import pytest
import json

from django.shortcuts import reverse
from django.contrib.contenttypes.models import ContentType

from ...manager.tests.utils import Topography1DFactory, Topography2DFactory, UserFactory, SurfaceFactory
from ...manager.models import Analysis, Topography, Surface
from ...manager.utils import subjects_to_dict
from ..models import AnalysisFunction
from ..functions import VIZ_SERIES
from .utils import TopographyAnalysisFactory, SurfaceAnalysisFactory


@pytest.mark.django_db
def test_series_card_data_sources(rf, handle_usage_statistics):
    from django.urls import get_resolver
    print(get_resolver().reverse_dict.keys())

    #
    # Create database objects
    #
    password = "secret"
    user = UserFactory(password=password)
    surface = SurfaceFactory(creator=user)
    func1 = AnalysisFunction.objects.get(name="test")

    topo1 = Topography2DFactory(surface=surface)

    analysis = TopographyAnalysisFactory(subject=topo1, function=func1, users=[user])

    request = rf.post(reverse(f'analysis:card/{VIZ_SERIES}'), data={
        'function_id': func1.id,
        'card_id': 'card',
        'template_flavor': 'detail',
        'subjects_ids_json': subjects_to_json([topo1]),
    }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    request.user = user
    response = PlotCardView.as_view()(request)

    data_sources = json.loads(response.context_data['data_sources'])

    exp_data_sources = [
        {
            "source_name": f"analysis-{analysis.id}",
            "subject_name": topo1.name,
            "subject_name_index": 0,
            "subject_name_has_parent": False,
            "series_name": "Fibonacci series",
            "series_name_index": 0,
            "xScaleFactor": 1,
            "yScaleFactor": 1,
            "url": reverse('analysis:data', kwargs=dict(pk=analysis.id, location="series-0.json")),
            "color": "#1f77b4", "dash": "solid", "width": 1, "alpha": 1.0,
            "showSymbols": True,
            "visible": True,
            "has_parent": False,
            "is_surface_analysis": False,
            "is_topography_analysis": True,
        },
        {
            "source_name": f"analysis-{analysis.id}",
            "subject_name": topo1.name,
            "subject_name_index": 0,
            "subject_name_has_parent": False,
            "series_name": "Geometric series",
            "series_name_index": 1,
            "xScaleFactor": 1,
            "yScaleFactor": 1,
            "url": reverse('analysis:data', kwargs=dict(pk=analysis.id, location="series-1.json")),
            "color": "#1f77b4", "dash": "dashed", "width": 1, "alpha": 1.0,
            "showSymbols": True,
            "visible": True,
            "has_parent": False,
            "is_surface_analysis": False,
            "is_topography_analysis": True
        }
    ]

    assert data_sources == exp_data_sources


@pytest.mark.django_db
def test_series_card_if_no_successful_topo_analysis(client, handle_usage_statistics):
    #
    # Create database objects
    #
    password = "secret"
    user = UserFactory(password=password)
    topography_ct = ContentType.objects.get_for_model(Topography)
    surface_ct = ContentType.objects.get_for_model(Surface)
    func1 = AnalysisFunction.objects.get(name="test")

    surf = SurfaceFactory(creator=user)
    topo = Topography1DFactory(surface=surf)  # also generates the surface

    # There is a successful surface analysis, but no successful topography analysis
    SurfaceAnalysisFactory(task_state='su', subject_id=topo.surface.id,
                           subject_type_id=surface_ct.id, function=func1, users=[user])

    # add a failed analysis for the topography
    TopographyAnalysisFactory(task_state='fa', subject_id=topo.id,
                              subject_type_id=topography_ct.id, function=func1, users=[user])

    assert Analysis.objects.filter(function=func1, subject_id=topo.id, subject_type_id=topography_ct.id,
                                   task_state='su').count() == 0
    assert Analysis.objects.filter(function=func1, subject_id=topo.id, subject_type_id=topography_ct.id,
                                   task_state='fa').count() == 1
    assert Analysis.objects.filter(function=func1, subject_id=topo.surface.id, subject_type_id=surface_ct.id,
                                   task_state='su').count() == 1

    # login and request plot card view
    assert client.login(username=user.username, password=password)

    response = client.post(reverse(f'analysis:card/{VIZ_SERIES}'), data={
        'function_id': func1.id,
        'card_id': 'card',
        'template_flavor': 'list',
        'subjects_ids_json': subjects_to_dict([topo, topo.surface]),  # also request results for surface here
    }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')  # we need an AJAX request

    # should return without errors
    assert response.status_code == 200
