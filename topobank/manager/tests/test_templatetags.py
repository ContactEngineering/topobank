import pytest
from django.urls import reverse, resolve

from .utils import SurfaceFactory, TopographyFactory
from ..templatetags.navbar_tags import navbar_active

@pytest.mark.django_db
def test_navbar_tags():

    surface = SurfaceFactory()
    topo = TopographyFactory(surface=surface)

    home_url = reverse('home')

    surface_list_url = reverse('manager:select')
    surface_detail_url = reverse('manager:surface-detail', kwargs=dict(pk=surface.pk))
    surface_delete_url = reverse('manager:surface-delete', kwargs=dict(pk=surface.pk))
    surface_update_url = reverse('manager:surface-update', kwargs=dict(pk=surface.pk))
    surface_share_url = reverse('manager:surface-share', kwargs=dict(pk=surface.pk))

    topography_create_url = reverse('manager:topography-create', kwargs=dict(surface_id=surface.id))
    topography_detail_url = reverse('manager:topography-detail', kwargs=dict(pk=topo.pk))
    topography_update_url = reverse('manager:topography-update', kwargs=dict(pk=topo.pk))
    topography_delete_url = reverse('manager:topography-delete', kwargs=dict(pk=topo.pk))

    analyses_url = reverse('analysis:list')
    sharing_url = reverse('manager:sharing-info')

    ACTIVE = "active"
    INACTIVE = ""

    # Test for "Surfaces" link
    assert navbar_active(surface_list_url, "Surfaces") == ACTIVE
    assert navbar_active(surface_detail_url, "Surfaces") == ACTIVE
    assert navbar_active(surface_update_url, "Surfaces") == ACTIVE
    assert navbar_active(surface_delete_url, "Surfaces") == ACTIVE
    assert navbar_active(surface_share_url, "Surfaces") == ACTIVE

    assert navbar_active(topography_create_url, "Surfaces") == ACTIVE
    assert navbar_active(topography_detail_url, "Surfaces") == ACTIVE
    assert navbar_active(topography_update_url, "Surfaces") == ACTIVE
    assert navbar_active(topography_delete_url, "Surfaces") == ACTIVE

    assert navbar_active(analyses_url, "Surfaces") == INACTIVE
    assert navbar_active(sharing_url, "Surfaces") == INACTIVE

    assert navbar_active(home_url, "Surfaces") == INACTIVE

    # Test for "Analyses" link
    assert navbar_active(surface_list_url, "Analyses") == INACTIVE
    assert navbar_active(analyses_url, "Analyses") == ACTIVE
    assert navbar_active(sharing_url, "Analyses") == INACTIVE

    assert navbar_active(home_url, "Analyses") == INACTIVE

    # Test for "Sharing" link
    assert navbar_active(surface_list_url, "Sharing") == INACTIVE
    assert navbar_active(analyses_url, "Sharing") == INACTIVE
    assert navbar_active(sharing_url, "Sharing") == ACTIVE

    assert navbar_active(home_url, "Sharing") == INACTIVE
