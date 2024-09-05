import pytest
from rest_framework.reverse import reverse

from topobank.analysis.models import Analysis, AnalysisFunction
from topobank.manager.utils import dict_to_base64, subjects_to_base64
from topobank.testing.factories import SurfaceFactory, Topography1DFactory, UserFactory


@pytest.mark.django_db
def test_dependencies(api_client, django_capture_on_commit_callbacks):
    """Test whether existing analyses can be renewed by API call."""

    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    topo1 = Topography1DFactory(surface=surface)

    func = AnalysisFunction.objects.get(name="Second test implementation")

    api_client.force_login(user)

    kwargs = {"c": 33, "d": 7.5}
    subjects_str = subjects_to_base64([topo1])
    kwargs_str = dict_to_base64(kwargs)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(
            f"{reverse('analysis:result-list')}?"
            f"subjects={subjects_str}&function_id={func.id}&"
            f"function_kwargs={kwargs_str}"
        )
        assert response.status_code == 200
    assert len(callbacks) == 1

    #
    # New Analysis objects should be there and marked for the user
    #
    assert Analysis.objects.count() == 3
    test2_ana, test_ana1, test_ana2 = Analysis.objects.all().order_by("function__name")
    assert test_ana1.task_state == Analysis.SUCCESS
    assert test_ana2.task_state == Analysis.SUCCESS
    assert test2_ana.task_state == Analysis.SUCCESS
    assert test_ana1.kwargs == {"a": 1, "b": 33 * "A"}  # b is c from test2 passed on
    assert test_ana2.kwargs == {"a": 33, "b": "foo"}  # a is c from test2 passed on
    assert test2_ana.kwargs == {"c": 33, "d": 7.5}
    assert test2_ana.result["result_from_dep"] == test_ana1.result["xunit"]
