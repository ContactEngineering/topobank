import pytest

from django.shortcuts import reverse
from django.contrib.contenttypes.models import ContentType

from topobank.manager.tests.utils import Topography1DFactory, UserFactory, SurfaceFactory
from topobank.manager.utils import subjects_to_json
from topobank.manager.models import Analysis, Topography, Surface

from .utils import AnalysisFunctionFactory, TopographyAnalysisFactory, SurfaceAnalysisFactory,\
    AnalysisFunctionImplementationFactory
from ..views import card_view_class, SimpleCardView, PlotCardView


@pytest.mark.django_db
def test_card_templates_simple(client, mocker, handle_usage_statistics):
    """Check whether correct template is selected."""

    #
    # Create database objects
    #
    password = "secret"
    user = UserFactory(password=password)
    func1 = AnalysisFunctionFactory(card_view_flavor='power spectrum')
    topo1 = Topography1DFactory()

    # An analysis function with card_view_flavor='power spectrum'
    # should use the template which is needed for PowerSpectrumCardView.
    #
    # For the "detail" mode, there is an own template for power spectrum,
    # which should be returned. The the "list" mode, there is no
    # special template. Therefore, since "PowerSpectrumCardView" is
    # derived from the "PlotCardView" so far, the resulting
    # template should be 'plot_card_list.html'.

    assert client.login(username=user.username, password=password)

    response = client.post(reverse('analysis:card'), data={
        'function_id': func1.id,
        'card_id': 'card',
        'template_flavor': 'list',
        'subjects_ids_json': subjects_to_json([topo1]),
    }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')  # we need an AJAX request

    assert response.template_name == ['analysis/plot_card_list.html']

    response = client.post(reverse('analysis:card'), data={
        'function_id': func1.id,
        'card_id': 'card',
        'template_flavor': 'detail',
        'subjects_ids_json': subjects_to_json([topo1]),
    }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')  # we need an AJAX request

    assert response.template_name == ['analysis/powerspectrum_card_detail.html']


@pytest.mark.django_db
def test_card_templates_for_power_spectrum(client, mocker, handle_usage_statistics):
    #
    # Create database objects
    #
    password = "secret"
    user = UserFactory(password=password)
    func1 = AnalysisFunctionFactory(card_view_flavor='power spectrum')
    topo1 = Topography1DFactory()

    assert client.login(username=user.username, password=password)

    response = client.post(reverse('analysis:card'), data={
        'function_id': func1.id,
        'card_id': 'card',
        'template_flavor': 'list',
        'subjects_ids_json': subjects_to_json([topo1]),
    }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')  # we need an AJAX request

    # we get the inherited "plot" template with "list" flavor, because power spectrum
    # hasn't got an own template with "list" flavor
    assert response.template_name == ['analysis/plot_card_list.html']

    response = client.post(reverse('analysis:card'), data={
        'function_id': func1.id,
        'card_id': 'card',
        'template_flavor': 'detail',
        'subjects_ids_json': subjects_to_json([topo1]),
    }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')  # we need an AJAX request

    # for the power spectrum detail card there should be an own template
    assert response.template_name == ['analysis/powerspectrum_card_detail.html']


@pytest.mark.django_db
def test_plot_card_if_no_successful_topo_analysis(client, handle_usage_statistics):
    #
    # Create database objects
    #
    password = "secret"
    user = UserFactory(password=password)
    topography_ct = ContentType.objects.get_for_model(Topography)
    surface_ct = ContentType.objects.get_for_model(Surface)
    func1 = AnalysisFunctionFactory(card_view_flavor='power spectrum')
    AnalysisFunctionImplementationFactory(function=func1, subject_type=topography_ct)
    AnalysisFunctionImplementationFactory(function=func1, subject_type=surface_ct)

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

    response = client.post(reverse('analysis:card'), data={
        'function_id': func1.id,
        'card_id': 'card',
        'template_flavor': 'list',
        'subjects_ids_json': subjects_to_json([topo, topo.surface]),  # also request results for surface here
    }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')  # we need an AJAX request

    # should return without errors
    assert response.status_code == 200


def test_card_view_class():
    assert card_view_class('simple') == SimpleCardView
    assert card_view_class('plot') == PlotCardView
