"""
Test whether analyses are recalculated on certain events.
"""
import pytest
from django.shortcuts import reverse

from .utils import TopographyFactory, SurfaceFactory, UserFactory


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






