"""
Tests related to thumbnails.
"""
import pytest

from django.shortcuts import reverse
from topobank.manager.tests.utils import Topography2DFactory, UserFactory, SurfaceFactory, Topography1DFactory
from topobank.utils import assert_no_form_errors


@pytest.mark.django_db
def test_thumbnail_exists_for_new_topography():
    topo = Topography2DFactory(size_x=1, size_y=1)
    # should have a thumbnail picture
    assert topo.thumbnail is not None


@pytest.mark.django_db
def test_renewal_on_topography_detrend_mode_change(client, mocker, django_capture_on_commit_callbacks):
    """Check whether thumbnail is renewed if detrend mode changes for a topography
    """

    from ..models import Topography
    renew_squeezed_mock = mocker.patch('topobank.manager.views.renew_squeezed_datafile.si')
    renew_bandwidth_cache_mock = mocker.patch('topobank.manager.views.renew_bandwidth_cache.si')
    renew_topo_analyses_mock = mocker.patch('topobank.manager.views.renew_analyses_related_to_topography.si')
    renew_topo_images_mock = mocker.patch('topobank.manager.views.renew_topography_images.si')

    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    topo = Topography1DFactory(surface=surface, size_y=1, detrend_mode='center')

    client.force_login(user)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = client.post(reverse('manager:topography-update', kwargs=dict(pk=topo.pk)),
                               data={
                                   'save-stay': 1,  # we want to save, but stay on page
                                   'surface': surface.pk,
                                   'data_source': 0,
                                   'name': topo.name,
                                   'measurement_date': topo.measurement_date,
                                   'description': "something",
                                   'size_x': 1,
                                   'size_y': 1,
                                   'unit': 'nm',
                                   'height_scale': 1,
                                   'detrend_mode': 'height',
                                   'instrument_type': Topography.INSTRUMENT_TYPE_UNDEFINED,
                                   'has_undefined_data': False,
                                   'fill_undefined_data_mode': Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING,
                               }, follow=True)

    # we just check here that the form is filled completely, otherwise the thumbnail would not be recreated too
    assert_no_form_errors(response)
    assert response.status_code == 200
    assert len(callbacks) == 1  # single chain for squeezed file, thumbnail and for analyses
    assert renew_topo_images_mock.called
    assert renew_topo_analyses_mock.called
    assert renew_squeezed_mock.called  # was directly called, not as callback from commit
    assert renew_bandwidth_cache_mock.called  # was directly called, not as callback from commit
