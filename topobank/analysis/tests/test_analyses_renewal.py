"""
Test whether analyses are recalculated on certain events.
"""

from pathlib import Path

import pytest
from django.shortcuts import reverse

from topobank.analysis.models import Analysis, AnalysisFunction
from topobank.analysis.tests.utils import SurfaceAnalysisFactory, Topography2DFactory, TopographyAnalysisFactory
from topobank.manager.models import Topography
from topobank.manager.tests.utils import FIXTURE_DIR, SurfaceFactory, Topography1DFactory, UserFactory, upload_file


@pytest.mark.parametrize("auto_renew", [True, False])
@pytest.mark.parametrize("changed_values_dict",
                         [  # would should be changed in POST request (->str values!)
                             ({
                                 "size_y": '100'
                             }),
                             ({
                                 "height_scale": '10',
                                 "instrument_type": 'microscope-based',
                             }),
                             # renew_squeezed should be called because of height_scale, not because of instrument_type
                             ({
                                 "instrument_type": 'microscope-based',  # instrument type changed at least
                                 'instrument_parameters': {"resolution": {"value": 1.0, "unit": "mm"}},
                             }),
                             ({
                                 'instrument_parameters': {"tip_radius": {"value": 2}},
                             }),
                             ({
                                 'instrument_parameters': {"tip_radius": {"unit": 'nm'}},
                             }),
                         ])
@pytest.mark.django_db
def test_renewal_on_topography_change(api_client, mocker, settings, django_capture_on_commit_callbacks,
                                      handle_usage_statistics, changed_values_dict, auto_renew):
    """Check whether methods for renewal are called on significant topography change.
    """
    settings.CELERY_TASK_ALWAYS_EAGER = True  # perform tasks locally
    settings.AUTOMATICALLY_RENEW_ANALYSES = auto_renew

    renew_topo_analyses_mock = mocker.patch('topobank.analysis.controller.submit_analysis')

    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    topo = Topography2DFactory(surface=surface, size_x=1, size_y=1, size_editable=True,
                               instrument_type=Topography.INSTRUMENT_TYPE_CONTACT_BASED,
                               instrument_parameters={
                                   "tip_radius": {
                                       "value": 1.0,
                                       "unit": "mm"
                                   }
                               })

    api_client.force_login(user)

    initial_data_for_post = {
        'data_source': topo.data_source,
        'description': topo.description,
        'name': topo.name,
        'size_x': topo.size_x,
        'size_y': topo.size_y,
        'height_scale': topo.height_scale,
        'detrend_mode': 'center',
        'measurement_date': format(topo.measurement_date, '%Y-%m-%d'),
        'tags': [],
        'instrument_name': '',
        'instrument_type': topo.instrument_type,
        'instrument_parameters': {"tip_radius": {"value": 1.0, "unit": "mm"}},
        'fill_undefined_data_mode': Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING,
        'has_undefined_data': False,
    }
    changed_data_for_post = initial_data_for_post.copy()

    # Reset mockers
    # renew_cache_mock.reset_mock()
    renew_topo_analyses_mock.reset_mock()

    # Update data
    changed_data_for_post.update(changed_values_dict)  # here is a change at least

    # if we post the initial data, nothing should have been changed, so no actions should be triggered
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.patch(reverse('manager:topography-api-detail', kwargs=dict(pk=topo.pk)),
                                    initial_data_for_post)
    assert response.status_code == 200

    assert len(callbacks) == 0
    # Nothing changed, so no callbacks

    renew_topo_analyses_mock.assert_not_called()

    #
    # now we post the changed data, some action (=callbacks) should be triggered
    #
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.patch(reverse('manager:topography-api-detail', kwargs=dict(pk=topo.pk)),
                                    changed_data_for_post)
    assert response.status_code == 200

    assert len(callbacks) == 1
    # one callbacks on commit expected:
    #   Renewing topography cache (thumbnail, DZI, etc.)

    if auto_renew:
        renew_topo_analyses_mock.assert_called()
        assert renew_topo_analyses_mock.call_count == AnalysisFunction.objects.count()  # Called once each
    else:
        renew_topo_analyses_mock.assert_not_called()
        assert renew_topo_analyses_mock.call_count == 0  # Never called


@pytest.mark.django_db
def test_analysis_removal_on_topography_deletion(api_client, test_analysis_function, handle_usage_statistics):
    """Check whether surface analyses are deleted if topography is deleted."""

    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    topo = Topography1DFactory(surface=surface)

    TopographyAnalysisFactory(subject_topography=topo, function=test_analysis_function)
    SurfaceAnalysisFactory(subject_surface=surface, function=test_analysis_function)
    SurfaceAnalysisFactory(subject_surface=surface, function=test_analysis_function)

    assert Analysis.objects.filter(subject_dispatch__topography=topo.id).count() == 1
    assert Analysis.objects.filter(subject_dispatch__surface=surface.id).count() == 2

    #
    # Now remove topography and see whether all analyses are deleted
    #
    api_client.force_login(user)

    response = api_client.delete(reverse('manager:topography-api-detail', kwargs=dict(pk=topo.pk)))

    assert response.status_code == 204

    assert surface.topography_set.count() == 0

    # No more topography analyses left
    assert Analysis.objects.filter(subject_dispatch__topography=topo).count() == 0
    # No more surface analyses left, because the surface no longer has topographies
    # The analysis of the surface is not deleting in this test, because the analysis does not actually run.
    # (Analysis run `on_commit`, but this is never triggered in this test.)
    # assert Analysis.objects.filter(subject_dispatch__surface=surface).count() == 0


@pytest.mark.parametrize("auto_renew", [True, False])
@pytest.mark.django_db
def test_renewal_on_topography_creation(api_client, mocker, settings, handle_usage_statistics,
                                        django_capture_on_commit_callbacks, auto_renew):
    settings.CELERY_TASK_ALWAYS_EAGER = True  # perform tasks locally
    settings.AUTOMATICALLY_RENEW_ANALYSES = auto_renew

    renew_topo_analyses_mock = mocker.patch('topobank.analysis.controller.submit_analysis')

    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    api_client.force_login(user)

    #
    # open first step of wizard: file upload
    #
    input_file_path = Path(FIXTURE_DIR + '/example-2d.npy')  # maybe use package 'pytest-datafiles' here instead
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = upload_file(str(input_file_path), surface.id, api_client, django_capture_on_commit_callbacks,
                               name='topo1',
                               measurement_date='2020-10-21',
                               data_source=0,
                               description="description",
                               size_x=1,
                               size_y=1,
                               unit='nm',
                               height_scale=1,
                               detrend_mode='height')
        assert response.data['name'] == 'topo1'
    assert len(callbacks) == 1  # renewing cached quantities

    if auto_renew:
        renew_topo_analyses_mock.assert_called()
        assert renew_topo_analyses_mock.call_count == 2 * AnalysisFunction.objects.count()
    else:
        renew_topo_analyses_mock.assert_not_called()
        assert renew_topo_analyses_mock.call_count == 0
