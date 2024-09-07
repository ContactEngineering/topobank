import pytest
from rest_framework.reverse import reverse

from topobank.analysis.models import Analysis, AnalysisFunction
from topobank.manager.utils import dict_to_base64, subjects_to_base64
from topobank.testing.factories import (
    SurfaceAnalysisFactory,
    SurfaceFactory,
    Topography1DFactory,
    TopographyAnalysisFactory,
    UserFactory,
)


@pytest.mark.django_db
def test_statistics(api_client, handle_usage_statistics):
    user = UserFactory()
    surf1 = SurfaceFactory(creator=user)
    surf2 = SurfaceFactory(creator=user)
    topo1a = Topography1DFactory(surface=surf1)
    topo1b = Topography1DFactory(surface=surf1)
    topo2a = Topography1DFactory(surface=surf2)

    func = AnalysisFunction.objects.get(name="Test implementation")

    #
    # Generate analyses for topographies with differing arguments
    #
    kwargs_1a = dict(a=1, b="abc")
    kwargs_1b = dict(a=1, b="def")  # differing from kwargs_1a!
    TopographyAnalysisFactory(
        subject_topography=topo1a, function=func, kwargs=kwargs_1a
    )
    TopographyAnalysisFactory(
        subject_topography=topo1b, function=func, kwargs=kwargs_1b
    )
    TopographyAnalysisFactory(
        subject_topography=topo2a, function=func
    )  # default arguments

    #
    # Generate analyses for surfaces with differing arguments
    #
    kwargs_1 = dict(a=2, b="abc")
    kwargs_2 = dict(a=2, b="def")  # differing from kwargs_1a!
    SurfaceAnalysisFactory(subject_surface=surf1, function=func, kwargs=kwargs_1)
    SurfaceAnalysisFactory(subject_surface=surf2, function=func, kwargs=kwargs_2)

    response = api_client.get(reverse("manager:statistics"))
    assert response.data["nb_users"] == 1
    assert response.data["nb_surfaces"] == 2
    assert response.data["nb_topographies"] == 3

    response = api_client.get(reverse("analysis:statistics"))
    assert response.data["nb_analyses"] == 5


@pytest.mark.django_db
def test_query_task_with_wrong_kwargs(
    api_client, one_line_scan, test_analysis_function
):
    user = one_line_scan.creator
    one_line_scan.grant_permission(user, "view")
    response = api_client.get(
        f"{reverse('analysis:result-list')}?subjects="
        f"{subjects_to_base64([one_line_scan])}&function_id={test_analysis_function.id}"
    )
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 0

    # Login
    api_client.force_login(user)
    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?subjects={subjects_to_base64([one_line_scan])}"
        f"&function_id={test_analysis_function.id}"
    )
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1

    # Get a different set of parameters
    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?subjects={subjects_to_base64([one_line_scan])}"
        f"&function_id={test_analysis_function.id}"
        f"&function_kwargs={dict_to_base64(dict(a=2, b='abc'))}"
    )
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1
    assert Analysis.objects.count() == 2

    # Try a parameter set that does not validate
    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?subjects={subjects_to_base64([one_line_scan])}"
        f"&function_id={test_analysis_function.id}"
        f"&function_kwargs={dict_to_base64(dict(a=2, c=7))}"
    )
    assert response.status_code == 400
    assert Analysis.objects.count() == 2


@pytest.mark.django_db
def test_function_info(api_client, user_alice, handle_usage_statistics):
    api_client.force_login(user_alice)

    response = api_client.get(
        f"{reverse('analysis:function-list')}?subject_type=topography"
    )

    assert response.status_code == 200
    assert len(response.data) > 0

    id = AnalysisFunction.objects.get(name="Test implementation").id

    response = api_client.get(reverse("analysis:function-detail", kwargs=dict(pk=id)))

    assert response.status_code == 200
    assert response.data == {
        "id": id,
        "url": f"http://testserver/analysis/api/function/{id}/",
        "name": "Test implementation",
        "visualization_type": "series",
        "kwargs_schema": {
            "a": {"default": 1, "title": "A", "type": "integer"},
            "b": {"default": "foo", "title": "B", "type": "string"},
        },
    }
