"""
Test whether analyses are recalculated on certain events.
"""
import pytest

from pathlib import Path
from django.shortcuts import reverse

from .utils import FIXTURE_DIR, TopographyFactory, SurfaceFactory, UserFactory
from topobank.utils import assert_in_content, assert_no_form_errors


@pytest.mark.django_db
def test_surface_analysis_renewal_on_topography_change(client, mocker):
    """Check whether methods for renewal are called on significant topography change.
    """

    renew_surf_analyses_mock = mocker.patch('topobank.manager.models.Surface.renew_analyses')
    renew_topo_analyses_mock = mocker.patch('topobank.manager.models.Topography.renew_analyses')

    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    topo = TopographyFactory(surface=surface, size_y=1)

    client.force_login(user)

    response = client.post(reverse('manager:topography-update', kwargs=dict(pk=topo.pk)),
                           data={
                               'save-stay': 1,  # we want to save, but stay on page
                               'surface': surface.pk,
                               'data_source': 0,
                               'name': topo.name,
                               'measurement_date': topo.measurement_date,
                               'description': "something",
                               'size_x': 1,
                               'size_y': 100,  # here is a change at least
                               'unit': 'nm',
                               'height_scale': 1,
                               'detrend_mode': 'center',
                           }, follow=True)

    assert response.status_code == 200

    assert renew_topo_analyses_mock.called
    assert renew_surf_analyses_mock.called


@pytest.mark.django_db
def test_surface_analysis_renewal_on_topography_deletion(client, mocker, handle_usage_statistics):
    """Check whether methods for renewal are called if topography is deleted.
    """

    renew_surf_analyses_mock = mocker.patch('topobank.manager.models.Surface.renew_analyses')

    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    topo = TopographyFactory(surface=surface)

    client.force_login(user)

    response = client.post(reverse('manager:topography-delete', kwargs=dict(pk=topo.pk)))

    assert response.status_code == 302
    assert renew_surf_analyses_mock.called


@pytest.mark.django_db
def test_surface_analysis_renewal_on_topography_creation(client, mocker, handle_usage_statistics):

    renew_surf_analyses_mock = mocker.patch('topobank.manager.models.Surface.renew_analyses')
    renew_topo_analyses_mock = mocker.patch('topobank.manager.models.Topography.renew_analyses')

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
                           }, follow=True)

    assert_no_form_errors(response)

    assert renew_topo_analyses_mock.called
    assert renew_surf_analyses_mock.called

