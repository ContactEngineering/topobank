"""
Test whether analyses are recalculated on certain events.
"""
import pytest

from pathlib import Path
from django.shortcuts import reverse
from django.contrib.contenttypes.models import ContentType

from .utils import FIXTURE_DIR, Topography1DFactory, SurfaceFactory, UserFactory
from ..models import Topography
from topobank.analysis.tests.utils import SurfaceAnalysisFactory, AnalysisFunctionFactory, \
    AnalysisFunctionImplementationFactory, TopographyAnalysisFactory, Topography2DFactory
from topobank.utils import assert_in_content, assert_no_form_errors


@pytest.mark.parametrize("changed_values_dict", [  # would should be changed in POST request (->str values!)
    {
        "size_y": '100'
    },
    {
        "instrument_type": 'microscope-based',  # instrument type changed at least
        "resolution_value": '1',
        "resolution_unit": 'mm',
    },
    {
        "tip_radius_value": '2',  # value changed
    },
    {
        "tip_radius_unit": 'nm',  # unit changed
    }
])
@pytest.mark.django_db
def test_renewal_on_topography_change(client, mocker, django_capture_on_commit_callbacks, handle_usage_statistics,
                                      changed_values_dict):
    """Check whether methods for renewal are called on significant topography change.
    """
    renew_topo_analyses_mock = mocker.patch('topobank.manager.views.renew_analyses_related_to_topography.delay')
    renew_topo_images_mock = mocker.patch('topobank.manager.views.renew_topography_images.delay')

    # The mock for renewing the squeezed datafile does not aim at the background task,
    # but directly to the method of the topography because this has to be done in foreground,
    # because the other steps (thumbnail, analyses) depend on the squeezed datafile
    from ..models import Topography
    renew_squeezed_method_mock = mocker.patch.object(Topography, 'renew_squeezed_datafile', return_value='patched')
    # we must mock the class not the topo object, because in the view another topography instance is created,
    # which is different from this one

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

    client.force_login(user)

    initial_data_for_post = {
        'save-stay': 'Save and keep editing',  # we want to save, but stay on page
        'surface': str(surface.pk),
        'data_source': str(topo.data_source),
        'description': topo.description,
        'name': topo.name,
        'size_x': str(topo.size_x),
        'size_y': str(topo.size_y),
        'size_editable': "True",
        'unit': topo.unit,
        'unit_editable': "True",
        'height_scale': str(topo.height_scale),
        'height_scale_editable': "True",
        'detrend_mode': 'center',
        'measurement_date': format(topo.measurement_date, '%Y-%m-%d'),
        'tags': '',
        'instrument_name': '',
        'instrument_type': topo.instrument_type,
        'instrument_parameters': '{"tip_radius": { "value": 1.0, "unit": "mm"} }',
        # add some helper fields which have been added to the form, such that
        # the POST request has all parameters as the original HTML form
        'tip_radius_value': '1.0',  # no change so far
        'tip_radius_unit': 'mm',  # no change so far
        'fill_undefined_data_mode': Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING,
        'has_undefined_data': False,
    }

    # also pass that? seems to be included in POST data on actual page
    # {
    #     "initial-instrument_parameters": "{}",
    #     "resolution_unit": "km",
    #     "resolution_value": "",
    #     "tip_radius_unit": "km",
    #     "tip_radius_value": "",
    #
    # }
    changed_data_for_post = initial_data_for_post.copy()

    changed_data_for_post.update(changed_values_dict)  # here is a change at least

    #
    # first get the form
    #
    response = client.get(reverse('manager:topography-update', kwargs=dict(pk=topo.pk)), follow=True)
    assert response.status_code == 200

    #
    # if we post the initial data, nothing should have been changed, so no actions should be triggered
    #
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = client.post(reverse('manager:topography-update', kwargs=dict(pk=topo.pk)),
                               data=initial_data_for_post, follow=True)
    assert_no_form_errors(response)
    assert response.status_code == 200

    assert len(callbacks) == 0
    # Nothing changed, so no callbacks

    assert not renew_squeezed_method_mock.called
    assert not renew_topo_analyses_mock.called
    assert not renew_topo_images_mock.called

    #
    # now we post the changed data, some action (=callbacks) should be triggered
    #
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = client.post(reverse('manager:topography-update', kwargs=dict(pk=topo.pk)),
                               data=changed_data_for_post, follow=True)
    assert_no_form_errors(response)
    assert response.status_code == 200

    assert len(callbacks) == 2
    # two callbacks on commit expected, see view

    assert renew_squeezed_method_mock.called
    assert renew_topo_analyses_mock.called
    assert renew_topo_images_mock.called


@pytest.mark.parametrize("changed_values_dict", [
    {
        "size_y": 100
    },
    {
        "instrument_type": 'microscope-based',  # instrument type changed at least
        "resolution_value": 1,
        "resolution_unit": 'mm',
    },
    {
        "tip_radius_value": 2,  # value changed
    },
    {
        "tip_radius_unit": 'nm',  # unit changed
    },
    {
        "fill_undefined_data_mode": Topography.FILL_UNDEFINED_DATA_MODE_HARMONIC,  # now harmonic
    },
])
@pytest.mark.django_db
def test_form_changed_when_input_changes(changed_values_dict):
    from ..models import Topography
    from ..forms import TopographyForm
    import datetime

    user = UserFactory()
    surface = SurfaceFactory(creator=user)

    initial_data = {
        'save-stay': 1,  # we want to save, but stay on page
        'surface': surface.pk,  # must be a valid choice
        'data_source': 0,
        'datafile': 'somefile',  # not relevant here
        'name': 'bla',
        'size_x': 1,
        'size_y': 2,
        'size_editable': True,
        'height_scale': 2,
        'height_scale_editable': True,
        'unit': 'mm',
        'unit_editable': True,
        'detrend_mode': 'center',
        'measurement_date': datetime.date(2021, 9, 24),
        'instrument_type': Topography.INSTRUMENT_TYPE_CONTACT_BASED,
        'instrument_parameters': {"tip_radius": {"value": 1, "unit": "mm"}},
        'resolution_value': '',
        'resolution_unit': '',
        'tip_radius_value': 1,  # no change so far
        'tip_radius_unit': 'mm',  # no change so far
        'fill_undefined_data_mode': Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING,
    }

    # if the initial data is passed as data, nothing has been changed
    form = TopographyForm(initial_data, initial=initial_data,
                          has_size_y=True, autocomplete_tags=[],
                          allow_periodic=False, has_undefined_data=None)
    assert form.is_valid(), form.errors
    # assert not form.has_changed(), (form.changed_data,
    #                                 [(form.data[k], form.initial[k], form.data[k] == form.initial[k])
    #                                  for k in form.changed_data])
    assert set(changed_values_dict.keys()).intersection(form.changed_data) == set()
    # somehow "instrument_parameters" is in changed_data, even if there is not change, don't know why

    # if we pass changed data, this should be detected
    form_data = initial_data.copy()
    form_data.update(changed_values_dict)  # here is a change at least  (besides 'instrument_parameters', see above)
    form = TopographyForm(form_data, initial=initial_data,
                          has_size_y=True, autocomplete_tags=[],
                          allow_periodic=False, has_undefined_data=None)

    assert form.is_valid(), form.errors
    assert set(changed_values_dict.keys()).intersection(form.changed_data) == set(changed_values_dict.keys())
    # all keys which have changed are included in form.changed_data + "instrument_parameters which is left out here


@pytest.mark.django_db
def test_analysis_removal_on_topography_deletion(client, handle_usage_statistics):
    """Check whether surface analyses are deleted if topography is deleted.
    """

    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    topo = Topography1DFactory(surface=surface)

    func = AnalysisFunctionFactory()
    AnalysisFunctionImplementationFactory(function=func,
                                          subject_type=ContentType.objects.get_for_model(topo))
    AnalysisFunctionImplementationFactory(function=func,
                                          subject_type=ContentType.objects.get_for_model(surface))
    TopographyAnalysisFactory(subject=topo, function=func)
    SurfaceAnalysisFactory(subject=surface, function=func)
    SurfaceAnalysisFactory(subject=surface, function=func)

    assert topo.analyses.count() == 1
    assert surface.analyses.count() == 2

    #
    # Now remove topography and see whether all analyses are deleted
    #
    client.force_login(user)

    response = client.post(reverse('manager:topography-delete', kwargs=dict(pk=topo.pk)))

    assert response.status_code == 302

    # No more topography analyses left
    assert topo.analyses.count() == 0
    # No more surface analyses left
    assert surface.analyses.count() == 0


@pytest.mark.django_db
def test_renewal_on_topography_creation(client, mocker, handle_usage_statistics, django_capture_on_commit_callbacks):
    renew_topo_analyses_mock = mocker.patch('topobank.manager.views.renew_analyses_related_to_topography.delay')
    renew_topo_images_mock = mocker.patch('topobank.manager.views.renew_topography_images.delay')

    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    client.force_login(user)

    #
    # open first step of wizard: file upload
    #
    input_file_path = Path(FIXTURE_DIR + '/example-2d.npy')  # maybe use package 'pytest-datafiles' here instead
    with open(str(input_file_path), mode='rb') as fp:
        response = client.post(reverse('manager:topography-create',
                                       kwargs=dict(surface_id=surface.id)),
                               data={
                                   'topography_create_wizard-current_step': 'upload',
                                   'upload-datafile': fp,
                                   'upload-datafile_format': '',
                                   'upload-surface': surface.id,
                               }, follow=True)

    assert response.status_code == 200
    assert_no_form_errors(response)

    #
    # now we should be on the page with second step
    #
    assert_in_content(response, "Step 2 of 3")
    assert_in_content(response, '<option value="0">Default</option>')
    assert response.context['form'].initial['name'] == 'example-2d.npy'

    #
    # Send data for second page
    #
    response = client.post(reverse('manager:topography-create',
                                   kwargs=dict(surface_id=surface.id)),
                           data={
                               'topography_create_wizard-current_step': 'metadata',
                               'metadata-name': 'topo1',
                               'metadata-measurement_date': '2020-10-21',
                               'metadata-data_source': 0,
                               'metadata-description': "description",
                           }, follow=True)
    assert_no_form_errors(response)

    #
    # Send data for third page
    #
    assert_in_content(response, "Step 3 of 3")
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = client.post(reverse('manager:topography-create',
                                       kwargs=dict(surface_id=surface.id)),
                               data={
                                   'topography_create_wizard-current_step': 'units',
                                   'units-size_x': '1',
                                   'units-size_y': '1',
                                   'units-unit': 'nm',
                                   'units-height_scale': 1,
                                   'units-detrend_mode': 'height',
                                   'units-resolution_x': 2,
                                   'units-resolution_y': 2,
                                   'units-instrument_type': 'undefined',
                                   'units-has_undefined_data': False,
                                   'units-fill_undefined_data_mode': Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING,
                               }, follow=True)

    assert_no_form_errors(response)

    assert len(callbacks) == 2  # for thumbnail and for analyses
    assert renew_topo_analyses_mock.called
    assert renew_topo_images_mock.called
