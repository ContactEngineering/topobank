"""Tests for topobank.manager.v2 filters."""

import pytest
from django.urls import reverse
from rest_framework import status

from topobank.testing.factories import SurfaceFactory, TagFactory, Topography1DFactory

# Topography Filtering Tests


@pytest.mark.django_db
def test_topography_list_filter_by_surface(api_client, user_alice):
    """Test filtering topographies by surface ID."""
    surface1 = SurfaceFactory(created_by=user_alice, name="Surface 1")
    surface2 = SurfaceFactory(created_by=user_alice, name="Surface 2")
    surface1.grant_permission(user_alice, "view")
    surface2.grant_permission(user_alice, "view")

    topo1 = Topography1DFactory(surface=surface1, created_by=user_alice, name="Topo 1")
    topo2 = Topography1DFactory(surface=surface1, created_by=user_alice, name="Topo 2")
    topo3 = Topography1DFactory(surface=surface2, created_by=user_alice, name="Topo 3")
    topo1.grant_permission(user_alice, "view")
    topo2.grant_permission(user_alice, "view")
    topo3.grant_permission(user_alice, "view")

    api_client.force_login(user_alice)
    url = reverse("manager:topography-v2-list")

    # Filter by surface1
    response = api_client.get(url, {"surface": surface1.id})
    assert response.status_code == status.HTTP_200_OK
    topo_ids = [t["id"] for t in response.data["results"]]
    assert topo1.id in topo_ids
    assert topo2.id in topo_ids
    assert topo3.id not in topo_ids

    # Filter by surface2
    response = api_client.get(url, {"surface": surface2.id})
    assert response.status_code == status.HTTP_200_OK
    topo_ids = [t["id"] for t in response.data["results"]]
    assert topo3.id in topo_ids
    assert topo1.id not in topo_ids


@pytest.mark.django_db
def test_topography_list_filter_by_tags(api_client, user_alice):
    """Test filtering topographies by tags."""

    # NOTE: Tags are associated with Surfaces
    tag1 = TagFactory(name="experiment")
    tag2 = TagFactory(name="simulation")
    tag3 = TagFactory(name="validation")

    surface1 = SurfaceFactory(created_by=user_alice)
    surface1.grant_permission(user_alice, "view")

    surface2 = SurfaceFactory(created_by=user_alice)
    surface2.grant_permission(user_alice, "view")

    surface3 = SurfaceFactory(created_by=user_alice)
    surface3.grant_permission(user_alice, "view")

    topo1 = Topography1DFactory(surface=surface1, created_by=user_alice, name="Exp Topo")
    topo1.tags.add(tag1)
    topo1.surface.tags.add(tag1)  # Also add tag to surface
    topo1.grant_permission(user_alice, "view")

    topo2 = Topography1DFactory(surface=surface2, created_by=user_alice, name="Sim Topo")
    topo2.tags.add(tag2)
    topo2.surface.tags.add(tag2)  # Also add tag to surface
    topo2.grant_permission(user_alice, "view")

    topo3 = Topography1DFactory(
        surface=surface3, created_by=user_alice, name="Val Topo"
    )
    topo3.tags.add(tag1, tag3)
    topo3.surface.tags.add(tag1, tag3)  # Also add tags to surface
    topo3.grant_permission(user_alice, "view")

    api_client.force_login(user_alice)
    url = reverse("manager:topography-v2-list")

    # No filter - sanity check
    response = api_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] >= 3

    # Filter by tag1 (experiment)
    response = api_client.get(url, {"tag": "experiment"})
    assert response.status_code == status.HTTP_200_OK
    topo_ids = [t["id"] for t in response.data["results"]]
    assert topo1.id in topo_ids
    assert topo3.id in topo_ids
    assert topo2.id not in topo_ids

    # Filter by tag2 (simulation)
    response = api_client.get(url, {"tag": "simulation"})
    assert response.status_code == status.HTTP_200_OK
    topo_ids = [t["id"] for t in response.data["results"]]
    assert topo2.id in topo_ids
    assert topo1.id not in topo_ids

    # Filter by tags starting with "exp"
    response = api_client.get(url, {"tag_startswith": "exp"})
    assert response.status_code == status.HTTP_200_OK
    topo_ids = [t["id"] for t in response.data["results"]]
    assert topo1.id in topo_ids
    assert topo3.id in topo_ids
    assert topo2.id not in topo_ids


@pytest.mark.django_db
def test_topography_list_filter_respects_permissions(
    api_client, user_alice, user_bob
):
    """Test that filtering respects user permissions."""
    tag = TagFactory(name="shared_topo_tag")

    surface_alice = SurfaceFactory(created_by=user_alice)
    surface_alice.grant_permission(user_alice, "view")
    topo_alice = Topography1DFactory(surface=surface_alice, created_by=user_alice)
    topo_alice.tags.add(tag)
    topo_alice.surface.tags.add(tag)  # Also add tag to surface
    topo_alice.grant_permission(user_alice, "view")

    surface_bob = SurfaceFactory(created_by=user_bob)
    surface_bob.grant_permission(user_bob, "view")
    topo_bob = Topography1DFactory(surface=surface_bob, created_by=user_bob)
    topo_bob.tags.add(tag)
    topo_bob.surface.tags.add(tag)  # Also add tag to surface
    topo_bob.grant_permission(user_bob, "view")

    api_client.force_login(user_alice)
    url = reverse("manager:topography-v2-list")

    # Even with tag filter, Alice should only see her topographies
    response = api_client.get(url, {"tag": "shared_topo_tag"})
    assert response.status_code == status.HTTP_200_OK
    topo_ids = [t["id"] for t in response.data["results"]]
    assert topo_alice.id in topo_ids
    assert topo_bob.id not in topo_ids
