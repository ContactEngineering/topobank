import pytest
from rest_framework.reverse import reverse

from topobank.analysis.models import Workflow, WorkflowResult
from topobank.manager.models import Tag
from topobank.manager.utils import dict_to_base64, subjects_to_base64
from topobank.testing.factories import (
    AnalysisFactory,
    SurfaceFactory,
    Topography1DFactory,
    UserFactory,
)
from topobank.testing.utils import ASSERT_EQUAL_IGNORE_VALUE, assert_dict_equal


@pytest.mark.django_db
def test_statistics(api_client, user_staff, handle_usage_statistics):
    user = UserFactory()
    surf1 = SurfaceFactory(created_by=user)
    surf2 = SurfaceFactory(created_by=user)
    topo1a = Topography1DFactory(surface=surf1)
    topo1b = Topography1DFactory(surface=surf1)
    topo2a = Topography1DFactory(surface=surf2)

    func = Workflow.objects.get(name="topobank.testing.test")

    #
    # Generate analyses for topographies with differing arguments
    #
    kwargs_1a = dict(a=1, b="abc")
    kwargs_1b = dict(a=1, b="def")  # differing from kwargs_1a!
    AnalysisFactory(subject_topography=topo1a, function=func, kwargs=kwargs_1a)
    AnalysisFactory(subject_topography=topo1b, function=func, kwargs=kwargs_1b)
    AnalysisFactory(subject_topography=topo2a, function=func)  # default arguments

    #
    # Generate analyses for surfaces with differing arguments
    #
    kwargs_1 = dict(a=2, b="abc")
    kwargs_2 = dict(a=2, b="def")  # differing from kwargs_1a!
    AnalysisFactory(subject_surface=surf1, function=func, kwargs=kwargs_1)
    AnalysisFactory(subject_surface=surf2, function=func, kwargs=kwargs_2)

    api_client.force_login(user_staff)
    response = api_client.get(reverse("manager:statistics"))
    # assert response.data["nb_users"] == 1
    assert response.data["nb_surfaces"] == 2
    assert response.data["nb_topographies"] == 3

    response = api_client.get(reverse("analysis:statistics"))
    assert response.data["nb_analyses"] == 5


@pytest.mark.django_db
def test_query_with_wrong_kwargs(api_client, one_line_scan, test_analysis_function):
    user = one_line_scan.created_by
    one_line_scan.grant_permission(user, "view")
    response = api_client.get(
        f"{reverse('analysis:result-list')}?topography={one_line_scan.id}"
        f"&workflow={test_analysis_function.name}"
    )
    assert response.status_code == 200, response.reason_phrase
    assert len(response.data["analyses"]) == 0

    # Login
    api_client.force_login(user)
    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?subjects={subjects_to_base64([one_line_scan])}"
        f"&workflow={test_analysis_function.name}"
    )
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1

    # Get a different set of parameters
    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?topography={one_line_scan.id}"
        f"&workflow={test_analysis_function.name}"
        f"&kwargs={dict_to_base64(dict(a=2, b='abc'))}"
    )
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1
    assert WorkflowResult.objects.count() == 2

    # Try passing integer parameters as strings
    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?subjects={subjects_to_base64([one_line_scan])}"
        f"&workflow={test_analysis_function.name}"
        f"&kwargs={dict_to_base64(dict(a='2', b='abc'))}"
    )
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1
    assert WorkflowResult.objects.count() == 2

    # Try a parameter set that does not validate
    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?subjects={subjects_to_base64([one_line_scan])}"
        f"&workflow={test_analysis_function.name}"
        f"&kwargs={dict_to_base64(dict(a=2, c=7))}"
    )
    assert response.status_code == 400
    assert WorkflowResult.objects.count() == 2


def test_query_with_partial_kwargs(api_client, one_line_scan, test_analysis_function):
    user = one_line_scan.created_by
    one_line_scan.grant_permission(user, "view")
    response = api_client.get(
        f"{reverse('analysis:result-list')}?topography={one_line_scan.id}"
        f"&workflow={test_analysis_function.name}"
    )
    assert response.status_code == 200, response.reason_phrase
    assert len(response.data["analyses"]) == 0

    # Login
    api_client.force_login(user)

    # Try querying with partial parameters
    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?subjects={subjects_to_base64([one_line_scan])}"
        f"&workflow={test_analysis_function.name}"
        f"&kwargs={dict_to_base64(dict(a=2))}"
    )
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1
    assert WorkflowResult.objects.count() == 1


@pytest.mark.django_db
def test_function_info(api_client, user_alice, handle_usage_statistics):
    api_client.force_login(user_alice)

    response = api_client.get(
        f"{reverse('analysis:workflow-list')}?subject_type=topography"
    )

    assert response.status_code == 200
    assert len(response.data) > 0

    name = "topobank.testing.test"
    response = api_client.get(
        reverse("analysis:workflow-detail", kwargs=dict(name=name))
    )

    assert response.status_code == 200
    assert_dict_equal(
        response.data,
        {
            "id": ASSERT_EQUAL_IGNORE_VALUE,
            "url": f"http://testserver/analysis/api/workflow/{name}/",
            "name": name,
            "display_name": "Test implementation",
            "kwargs_schema": {
                "title": ASSERT_EQUAL_IGNORE_VALUE,
                "additionalProperties": False,
                "type": "object",
                "properties": {
                    "a": {"default": 1, "title": "A", "type": "integer"},
                    "b": {"default": "foo", "title": "B", "type": "string"},
                },
            },
            "outputs_schema": [],
        },
    )


@pytest.mark.django_db
def test_query_tag_analysis(
    api_client,
    one_line_scan,
    test_analysis_function,
    django_capture_on_commit_callbacks,
    handle_usage_statistics,
):
    user = one_line_scan.created_by
    # Add tag to surface
    one_line_scan.surface.tags.add("my-tag")
    tag = Tag.objects.get(name="my-tag")

    assert WorkflowResult.objects.count() == 0

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(
            f"{reverse('analysis:result-list')}?subjects="
            f"{subjects_to_base64([tag])}&workflow={test_analysis_function.name}"
        )
    assert len(callbacks) == 1
    assert WorkflowResult.objects.count() == 1
    # Tag analyses always succeed...
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1
    analysis_id = response.data["analyses"][0]["id"]
    # ...but they may have run on no data
    folder_url = response.data["analyses"][0]["folder"]
    response = api_client.get(folder_url)
    assert response.status_code == 200
    assert len(response.data) == 1
    assert "result.json" in response.data
    # Check that result file actually has no data
    # response = api_client.get(response.data["result.json"]["file"])
    # assert response.status_code == 200
    # assert len(response.data["analyses"]) == 1
    # file = response.data["result.json"]["file"][23:]
    analysis = WorkflowResult.objects.get(id=analysis_id)
    assert len(analysis.result["surfaces"]) == 0

    # Login
    api_client.force_login(user)
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(
            f"{reverse('analysis:result-list')}"
            f"?subjects={subjects_to_base64([tag])}"
            f"&workflow={test_analysis_function.name}"
        )
    assert len(callbacks) == 1
    assert WorkflowResult.objects.count() == 2
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1
    analysis_id = response.data["analyses"][0]["id"]
    unique_kwargs = response.data["unique_kwargs"]

    # ...but they may have run on no data
    folder_url = response.data["analyses"][0]["folder"]
    response = api_client.get(folder_url)
    assert response.status_code == 200
    assert len(response.data) == 1
    assert "result.json" in response.data
    # Check that result file actually has data now
    # response = api_client.get(response.data["result.json"]["file"])
    # assert response.status_code == 200
    # assert len(response.data["analyses"]) == 1
    # file = response.data["result.json"]["file"][23:]
    # data = json.load(default_storage.open(file))
    # assert len(data["surfaces"] == 1)
    analysis = WorkflowResult.objects.get(id=analysis_id)
    assert len(analysis.result["surfaces"]) == 1

    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?subjects={subjects_to_base64([tag])}"
        f"&workflow={test_analysis_function.name}"
        f"&kwargs={dict_to_base64(unique_kwargs)}"
    )
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1
    assert response.data["analyses"][0]["id"] == analysis_id  # Should yield the same


@pytest.mark.django_db
def test_query_with_unique_kwargs(
    api_client, one_line_scan, test_analysis_function, handle_usage_statistics
):
    user = one_line_scan.created_by
    one_line_scan.grant_permission(user, "view")
    response = api_client.get(
        f"{reverse('analysis:result-list')}?subjects="
        f"{subjects_to_base64([one_line_scan])}&workflow={test_analysis_function.name}"
    )
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 0

    # Login
    api_client.force_login(user)
    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?subjects={subjects_to_base64([one_line_scan])}"
        f"&workflow={test_analysis_function.name}"
    )
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1
    assert WorkflowResult.objects.count() == 1

    analysis_id = response.data["analyses"][0]["id"]
    unique_kwargs = response.data["unique_kwargs"]

    # Query again, but now with unique kwargs
    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?subjects={subjects_to_base64([one_line_scan])}"
        f"&workflow={test_analysis_function.name}"
        f"&kwargs={dict_to_base64(unique_kwargs)}"
    )
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1
    assert WorkflowResult.objects.count() == 1
    assert response.data["analyses"][0]["id"] == analysis_id  # Should yield the same


@pytest.mark.django_db
def test_query_with_error(
    api_client,
    one_line_scan,
    django_capture_on_commit_callbacks,
    handle_usage_statistics,
):
    user = one_line_scan.created_by
    function = Workflow.objects.get(name="topobank.testing.test_error")

    # Login
    api_client.force_login(user)
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(
            f"{reverse('analysis:result-list')}"
            f"?topography={one_line_scan.id}"
            f"&workflow={function.name}"
        )
    assert len(callbacks) == 1
    assert response.status_code == 200
    assert response.data["analyses"][0]["task_state"] == "pe"
    assert len(response.data["analyses"]) == 1
    assert WorkflowResult.objects.count() == 1

    # Second request is required to retrieve error (first is always pending)
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(
            f"{reverse('analysis:result-list')}"
            f"?topography={one_line_scan.id}"
            f"&workflow={function.name}"
        )
    assert len(callbacks) == 0  # This just return the error
    assert response.status_code == 200
    assert response.data["analyses"][0]["task_state"] == "fa"
    assert len(response.data["analyses"]) == 1
    assert WorkflowResult.objects.count() == 1

    assert response.data["analyses"][0]["task_error"] == "An error occurred!"
    assert "return runner.eval" in response.data["analyses"][0]["task_traceback"]


@pytest.mark.django_db
def test_query_with_error_in_dependency(
    api_client,
    one_line_scan,
    django_capture_on_commit_callbacks,
    handle_usage_statistics,
):
    user = one_line_scan.created_by
    function = Workflow.objects.get(
        name="topobank.testing.test_error_in_dependency"
    )

    # Login
    api_client.force_login(user)
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(
            f"{reverse('analysis:result-list')}"
            f"?topography={one_line_scan.id}"
            f"&workflow={function.name}"
        )
    assert len(callbacks) == 1
    assert response.status_code == 200
    assert response.data["analyses"][0]["task_state"] == "pe"
    assert len(response.data["analyses"]) == 1
    assert WorkflowResult.objects.count() == 2

    # Second request is required to retrieve error (first is always pending)
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(
            f"{reverse('analysis:result-list')}"
            f"?topography={one_line_scan.id}"
            f"&workflow={function.name}"
        )
    assert len(callbacks) == 0  # This just return the error
    assert response.status_code == 200
    assert response.data["analyses"][0]["task_state"] == "fa"
    assert len(response.data["analyses"]) == 1
    assert WorkflowResult.objects.count() == 2

    assert response.data["analyses"][0]["task_error"] == "An error occurred!"
    # Traceback should be passed up from the dependency
    assert response.data["analyses"][0]["task_traceback"] is not None


@pytest.mark.django_db
def test_save_tag_analysis(
    api_client,
    one_line_scan,
    test_analysis_function,
    django_capture_on_commit_callbacks,
    handle_usage_statistics,
):
    user = one_line_scan.created_by
    # Add tag to surface
    one_line_scan.surface.tags.add("my-tag")
    tag = Tag.objects.get(name="my-tag")

    assert WorkflowResult.objects.count() == 0

    # Login
    api_client.force_login(user)
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(
            f"{reverse('analysis:result-list')}"
            f"?subjects={subjects_to_base64([tag])}"
            f"&workflow={test_analysis_function.name}"
        )
    assert len(callbacks) == 1
    assert WorkflowResult.objects.count() == 1
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1
    set_name_url = response.data["analyses"][0]["api"]["set_name"]

    # Check that named result does not return unnamed results
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(reverse("analysis:named-result-list"))
    assert len(callbacks) == 0
    assert WorkflowResult.objects.count() == 1  # We still have one (the saved analysis)
    assert response.status_code == 200
    assert len(response.data) == 0

    # Set analysis name and description
    response = api_client.post(
        set_name_url, {"name": "my-name", "description": "my-description"}
    )
    assert response.status_code == 200
    assert WorkflowResult.objects.count() == 1  # This does not make a copy
    assert WorkflowResult.objects.get(name="my-name").description == "my-description"

    # Check that query the analysis again triggers a new one
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(
            f"{reverse('analysis:result-list')}"
            f"?subjects={subjects_to_base64([tag])}"
            f"&workflow={test_analysis_function.name}"
        )
    assert len(callbacks) == 1
    assert WorkflowResult.objects.count() == 2  # We now have two
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1

    # Delete tag
    tag.delete()
    assert WorkflowResult.objects.count() == 1

    # Check that we can query saved analysis
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(
            f"{reverse('analysis:named-result-list')}" f"?name=my-name"
        )
    assert len(callbacks) == 0
    assert WorkflowResult.objects.count() == 1  # We still have one (the saved analysis)
    assert response.status_code == 200
    assert len(response.data) == 1


@pytest.mark.django_db
def test_query_pending(
    api_client,
    one_line_scan,
    test_analysis_function,
    handle_usage_statistics,
):
    user = one_line_scan.created_by
    # Add tag to surface
    one_line_scan.surface.tags.add("my-tag")
    tag = Tag.objects.get(name="my-tag")

    assert WorkflowResult.objects.count() == 0

    # Login
    api_client.force_login(user)
    api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?subjects={subjects_to_base64([tag])}"
        f"&workflow={test_analysis_function.name}"
    )
    response = api_client.get(reverse("analysis:pending"))
    assert len(response.data) == 1
    assert response.data[0]["task_state"] == "pe"


@pytest.mark.django_db
def test_query_with_not_implemented_subject(
    api_client, one_line_scan, test_analysis_function
):
    user = one_line_scan.created_by
    one_line_scan.grant_permission(user, "view")
    surface = one_line_scan.surface
    response = api_client.get(
        f"{reverse('analysis:result-list')}?surface={surface.id}"
        f"&workflow=topobank.testing.topography_only_test"
    )
    assert response.status_code == 200
    assert response.data["analyses"] == []
