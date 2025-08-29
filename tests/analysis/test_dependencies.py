import celery.states
import pytest
from django.test import override_settings
from rest_framework.reverse import reverse

from topobank.analysis.models import Analysis, Workflow
from topobank.analysis.tasks import perform_analysis
from topobank.manager.utils import dict_to_base64, subjects_to_base64
from topobank.testing.factories import SurfaceFactory, Topography1DFactory, UserFactory


@pytest.mark.django_db
def test_dependencies(api_client, django_capture_on_commit_callbacks):
    """Test whether existing analyses can be renewed by API call."""

    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    topo1 = Topography1DFactory(surface=surface)

    func = Workflow.objects.get(name="topobank.testing.test2")

    api_client.force_login(user)

    kwargs = {"c": 33, "d": 7.5}
    subjects_str = subjects_to_base64([topo1])
    kwargs_str = dict_to_base64(kwargs)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(
            f"{reverse('analysis:result-list')}?"
            f"subjects={subjects_str}&workflow={func.name}&"
            f"kwargs={kwargs_str}"
        )
        assert response.status_code == 200, response.reason_phrase
    assert len(callbacks) == 1

    #
    # New Analysis objects should be there and marked for the user
    #
    assert Analysis.objects.count() == 3
    test_ana1, test_ana2, test2_ana = Analysis.objects.all().order_by("function__name")
    assert test2_ana.function.name == "topobank.testing.test2"
    assert test_ana1.function.name == "topobank.testing.test"
    assert test_ana2.function.name == "topobank.testing.test"
    assert test_ana1.task_state == Analysis.SUCCESS
    assert test_ana2.task_state == Analysis.SUCCESS
    assert test2_ana.task_state == Analysis.SUCCESS
    assert test_ana1.kwargs == {"a": 1, "b": 33 * "A"} or test_ana1.kwargs == {
        "a": 33,
        "b": "foo",
    }  # b is c from test2 passed on
    assert test_ana2.kwargs == {"a": 1, "b": 33 * "A"} or test_ana2.kwargs == {
        "a": 33,
        "b": "foo",
    }  # a is c from test2 passed on
    assert test2_ana.kwargs == {"c": 33, "d": 7.5}
    assert test2_ana.result["result_from_dep"] == test_ana1.result["xunit"]


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)  # We don't want to execute the chord
@pytest.mark.django_db
def test_dependency_status():
    """Test whether existing analyses can be renewed by API call."""

    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    topo1 = Topography1DFactory(surface=surface)

    func = Workflow.objects.get(name="topobank.testing.test2")

    kwargs = {"c": 33, "d": 7.5}
    analysis = func.submit(user, topo1, kwargs)
    # `perform_analysis` is not executed because it is run on commit
    task = perform_analysis.apply(args=(analysis.id, False))
    assert task.state == celery.states.SUCCESS

    #
    # New Analysis objects should be there and marked for the user
    #
    assert Analysis.objects.count() == 3
    test_ana1, test_ana2, test2_ana = Analysis.objects.all().order_by("function__name")
    assert test2_ana.function.name == "topobank.testing.test2"
    assert test_ana1.function.name == "topobank.testing.test"
    assert test_ana2.function.name == "topobank.testing.test"
    assert test2_ana.get_task_state() == Analysis.STARTED
    assert test_ana1.task_state == Analysis.PENDING
    assert test_ana2.task_state == Analysis.PENDING
    assert test_ana1.kwargs == {"a": 1, "b": 33 * "A"} or test_ana1.kwargs == {
        "a": 33,
        "b": "foo",
    }  # b is c from test2 passed on
    assert test_ana2.kwargs == {"a": 1, "b": 33 * "A"} or test_ana2.kwargs == {
        "a": 33,
        "b": "foo",
    }  # a is c from test2 passed on
    assert test2_ana.kwargs == {"c": 33, "d": 7.5}

    #
    # Check that dependency progress configuration looks good
    #
    assert test_ana1.launcher_task_id is None
    assert test_ana2.launcher_task_id is None


@pytest.mark.django_db
def test_error_propagation(
    api_client, django_capture_on_commit_callbacks, handle_usage_statistics
):
    """Test whether errors propagate from dependencies."""

    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    topo1 = Topography1DFactory(surface=surface)

    func = Workflow.objects.get(
        name="topobank.testing.test_error_in_dependency"
    )

    kwargs = {"c": 33, "d": 7.5}
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        analysis = func.submit(user, topo1, kwargs)
    assert len(callbacks) == 1
    # `perform_analysis` is not executed because it is run on commit
    task = perform_analysis.apply(args=(analysis.id, False))
    assert task.state == celery.states.SUCCESS

    #
    # New Analysis objects should be there and marked for the user
    #
    assert Analysis.objects.count() == 2
    test_ana1, test_ana2 = Analysis.objects.all().order_by("function__name")
    assert test_ana1.function.name == "topobank.testing.test_error"
    assert test_ana2.function.name == "topobank.testing.test_error_in_dependency"
    assert test_ana1.dependencies == {}
    assert test_ana2.dependencies == {"dep": test_ana1.id}
    assert test_ana1.get_task_state() == Analysis.FAILURE
    assert test_ana2.get_task_state() == Analysis.FAILURE
    assert test_ana1.task_state == Analysis.FAILURE
    assert test_ana2.task_state == Analysis.FAILURE
    assert test_ana1.kwargs == {
        "c": 33,
        "d": 7.5,
    }
    assert test_ana2.kwargs == {
        "c": 33,
        "d": 7.5,
    }

    api_client.force_login(user)
    result = api_client.get(reverse("analysis:result-detail", args=[test_ana2.id]))
    assert result.data["dependencies_url"] == reverse(
        "analysis:dependencies", args=[test_ana2.id], request=result.wsgi_request
    )
    result = api_client.get(result.data["dependencies_url"])
    assert result.data == {"dep": test_ana1.get_absolute_url(result.wsgi_request)}
