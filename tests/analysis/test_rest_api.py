import pytest
from rest_framework.reverse import reverse

from topobank.analysis.models import Analysis, AnalysisFunction
from topobank.manager.models import Tag
from topobank.manager.utils import dict_to_base64, subjects_to_base64
from topobank.testing.factories import (
    AnalysisFactory,
    SurfaceFactory,
    Topography1DFactory,
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

    response = api_client.get(reverse("manager:statistics"))
    # assert response.data["nb_users"] == 1
    assert response.data["nb_surfaces"] == 2
    assert response.data["nb_topographies"] == 3

    response = api_client.get(reverse("analysis:statistics"))
    assert response.data["nb_analyses"] == 5


@pytest.mark.django_db
def test_query_with_wrong_kwargs(api_client, one_line_scan, test_analysis_function):
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
        f"?topography={one_line_scan.id}"
        f"&function_id={test_analysis_function.id}"
        f"&function_kwargs={dict_to_base64(dict(a=2, b='abc'))}"
    )
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1
    assert Analysis.objects.count() == 2

    # Try passing integer parameters as strings
    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?subjects={subjects_to_base64([one_line_scan])}"
        f"&function_id={test_analysis_function.id}"
        f"&function_kwargs={dict_to_base64(dict(a='2', b='abc'))}"
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


@pytest.mark.django_db
def test_query_tag_analysis(
    api_client,
    one_line_scan,
    test_analysis_function,
    django_capture_on_commit_callbacks,
    handle_usage_statistics,
):
    user = one_line_scan.creator
    # Add tag to surface
    one_line_scan.surface.tags.add("my-tag")
    tag = Tag.objects.get(name="my-tag")

    assert Analysis.objects.count() == 0

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(
            f"{reverse('analysis:result-list')}?subjects="
            f"{subjects_to_base64([tag])}&function_id={test_analysis_function.id}"
        )
    assert len(callbacks) == 1
    assert Analysis.objects.count() == 1
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
    analysis = Analysis.objects.get(id=analysis_id)
    assert len(analysis.result["surfaces"]) == 0

    # Login
    api_client.force_login(user)
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(
            f"{reverse('analysis:result-list')}"
            f"?subjects={subjects_to_base64([tag])}"
            f"&function_id={test_analysis_function.id}"
        )
    assert len(callbacks) == 1
    assert Analysis.objects.count() == 2
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
    analysis = Analysis.objects.get(id=analysis_id)
    assert len(analysis.result["surfaces"]) == 1

    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?subjects={subjects_to_base64([tag])}"
        f"&function_id={test_analysis_function.id}"
        f"&function_kwargs={dict_to_base64(unique_kwargs)}"
    )
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1
    assert response.data["analyses"][0]["id"] == analysis_id  # Should yield the same


@pytest.mark.django_db
def test_query_with_unique_kwargs(
    api_client, one_line_scan, test_analysis_function, handle_usage_statistics
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
    assert Analysis.objects.count() == 1

    analysis_id = response.data["analyses"][0]["id"]
    unique_kwargs = response.data["unique_kwargs"]

    # Query again, but now with unique kwargs
    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?subjects={subjects_to_base64([one_line_scan])}"
        f"&function_id={test_analysis_function.id}"
        f"&function_kwargs={dict_to_base64(unique_kwargs)}"
    )
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1
    assert Analysis.objects.count() == 1
    assert response.data["analyses"][0]["id"] == analysis_id  # Should yield the same
