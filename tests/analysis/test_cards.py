import pytest
from django.contrib.contenttypes.models import ContentType
from rest_framework.reverse import reverse

from topobank.analysis.models import Workflow, WorkflowResult
from topobank.analysis.workflows import VIZ_SERIES
from topobank.manager.models import Surface, Topography
from topobank.manager.utils import subjects_to_base64
from topobank.testing.factories import (
    AnalysisSubjectFactory,
    SurfaceAnalysisFactory,
    SurfaceFactory,
    Topography1DFactory,
    Topography2DFactory,
    TopographyAnalysisFactory,
    UserFactory,
)


@pytest.mark.skip("URL does not resolve correctly in CI")
@pytest.mark.django_db
def test_series_card_data_sources(api_client, handle_usage_statistics):
    #
    # Create database objects
    #
    password = "secret"
    user = UserFactory(password=password)
    surface = SurfaceFactory(created_by=user)
    func1 = Workflow.objects.get(name="topobank.testing.test")

    topo1 = Topography2DFactory(surface=surface)

    analysis = TopographyAnalysisFactory(
        subject_topography=topo1, function=func1, user=user
    )

    #
    # login and request plot card view
    #
    assert api_client.login(username=user.username, password=password)

    url = (
        reverse(f"analysis:card-{VIZ_SERIES}", kwargs=dict(function_id=func1.id))
        + "?subjects="
        + subjects_to_base64([topo1])
    )
    response = api_client.get(url)

    data_sources = response.data["plotConfiguration"]["dataSources"]

    exp_data_sources = [
        {
            "sourceName": f"analysis-{analysis.id}",
            "subjectName": topo1.name,
            "subjectNameIndex": 0,
            "subjectNameHasParent": False,
            "seriesName": "Fibonacci series",
            "seriesNameIndex": 0,
            "xScaleFactor": 1,
            "yScaleFactor": 1,
            "url": reverse(
                "analysis:data",
                kwargs=dict(pk=analysis.id, location="series-0.json"),
                request=response.wsgi_request,
            ),
            "width": 1,
            "alpha": 1.0,
            "visible": True,
            "hasParent": False,
            "isSurfaceAnalysis": False,
            "isTopographyAnalysis": True,
        },
        {
            "sourceName": f"analysis-{analysis.id}",
            "subjectName": topo1.name,
            "subjectNameIndex": 0,
            "subjectNameHasParent": False,
            "seriesName": "Geometric series",
            "seriesNameIndex": 1,
            "xScaleFactor": 1,
            "yScaleFactor": 1,
            "url": reverse(
                "analysis:data",
                kwargs=dict(pk=analysis.id, location="series-1.json"),
                request=response.wsgi_request,
            ),
            "width": 1,
            "alpha": 1.0,
            "visible": True,
            "hasParent": False,
            "isSurfaceAnalysis": False,
            "isTopographyAnalysis": True,
        },
    ]

    assert data_sources == exp_data_sources


@pytest.mark.django_db
def test_series_card_if_no_successful_topo_analysis(
    api_client, handle_usage_statistics
):
    #
    # Create database objects
    #
    password = "secret"
    user = UserFactory(password=password)
    ContentType.objects.get_for_model(Topography)
    ContentType.objects.get_for_model(Surface)
    func1 = Workflow.objects.get(name="topobank.testing.test")

    surf = SurfaceFactory(created_by=user)
    topo = Topography1DFactory(surface=surf)  # also generates the surface

    # There is a successful surface analysis, but no successful topography analysis
    SurfaceAnalysisFactory(
        task_state="su",
        subject_dispatch=AnalysisSubjectFactory(surface_id=topo.surface.id),
        function=func1,
        user=user,
    )

    # add a failed analysis for the topography
    TopographyAnalysisFactory(
        task_state="fa",
        subject_dispatch=AnalysisSubjectFactory(topography_id=topo.id),
        function=func1,
        user=user,
    )

    assert (
        WorkflowResult.objects.filter(
            function=func1, subject_dispatch__topography_id=topo.id, task_state="su"
        ).count()
        == 0
    )
    assert (
        WorkflowResult.objects.filter(
            function=func1, subject_dispatch__topography_id=topo.id, task_state="fa"
        ).count()
        == 1
    )
    assert (
        WorkflowResult.objects.filter(
            function=func1,
            subject_dispatch__surface_id=topo.surface.id,
            task_state="su",
        ).count()
        == 1
    )

    # login and request plot card view
    assert api_client.login(username=user.username, password=password)

    response = api_client.get(
        reverse(f"analysis:card-{VIZ_SERIES}", kwargs=dict(workflow=func1.name))
        + "?subjects="
        + subjects_to_base64([topo, topo.surface])
    )  # also request results for surface here

    # should return without errors
    assert response.status_code == 200
