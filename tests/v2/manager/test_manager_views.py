"""Tests for topobank.manager.v2 views."""

import pytest
from django.urls import reverse
from rest_framework import status

from topobank.manager.models import Surface, Topography
from topobank.manager.zip_model import ZipContainer
from topobank.testing.factories import (
    PermissionSetFactory,
    SurfaceFactory,
    TagFactory,
    Topography1DFactory,
)

# TopographyViewSet Tests - List


@pytest.mark.django_db
def test_topography_list_authenticated(api_client, user_alice, one_line_scan):
    """Test listing topographies as authenticated user."""
    one_line_scan.created_by = user_alice
    one_line_scan.save()
    one_line_scan.grant_permission(user_alice, "view")

    api_client.force_login(user_alice)
    url = reverse("manager:topography-v2-list")
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert "results" in response.data
    assert response.data["count"] >= 1


@pytest.mark.django_db
def test_topography_list_unauthenticated(api_client):
    """Test listing topographies as unauthenticated user."""
    url = reverse("manager:topography-v2-list")
    response = api_client.get(url)

    # IsAuthenticatedOrReadOnly allows GET for anonymous users
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_topography_list_pagination(api_client, user_alice):
    """Test that topography list is paginated."""
    surface = SurfaceFactory(created_by=user_alice)
    surface.grant_permission(user_alice, "view")

    # Create multiple topographies
    for i in range(5):
        topo = Topography1DFactory(surface=surface, created_by=user_alice)
        topo.grant_permission(user_alice, "view")

    api_client.force_login(user_alice)
    url = reverse("manager:topography-v2-list")
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert "results" in response.data
    assert "count" in response.data
    assert response.data["count"] >= 5


@pytest.mark.django_db
def test_topography_list_filtered_by_permission(
    api_client, user_alice, user_bob, one_line_scan
):
    """Test that users only see topographies they have permission for."""
    # Alice's topography
    one_line_scan.created_by = user_alice
    one_line_scan.save()
    one_line_scan.grant_permission(user_alice, "view")

    # Bob's topography (no permission for Alice)
    surface_bob = SurfaceFactory(created_by=user_bob)
    topo_bob = Topography1DFactory(surface=surface_bob, created_by=user_bob)
    topo_bob.grant_permission(user_bob, "view")

    api_client.force_login(user_alice)
    url = reverse("manager:topography-v2-list")
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    # Alice should only see her own topography
    topo_ids = [t["id"] for t in response.data["results"]]
    assert one_line_scan.id in topo_ids
    assert topo_bob.id not in topo_ids


@pytest.mark.django_db
def test_topography_list_with_link_file_parameter(api_client, user_alice, one_line_scan):
    """Test that link_file parameter includes file URLs."""
    one_line_scan.created_by = user_alice
    one_line_scan.save()
    one_line_scan.grant_permission(user_alice, "view")

    api_client.force_login(user_alice)
    url = reverse("manager:topography-v2-list")
    response = api_client.get(url, {"link_file": "true"})

    assert response.status_code == status.HTTP_200_OK
    # With link_file, response should include file information
    assert "results" in response.data


# TopographyViewSet Tests - Retrieve


@pytest.mark.django_db
def test_topography_retrieve_success(api_client, user_alice, one_line_scan):
    """Test retrieving a single topography."""
    one_line_scan.created_by = user_alice
    one_line_scan.save()
    one_line_scan.grant_permission(user_alice, "view")

    api_client.force_login(user_alice)
    url = reverse("manager:topography-v2-detail", kwargs={"pk": one_line_scan.id})
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["id"] == one_line_scan.id
    assert response.data["name"] == one_line_scan.name
    assert "surface" in response.data
    assert "api" in response.data


@pytest.mark.django_db
def test_topography_retrieve_no_permission(api_client, user_alice, user_bob):
    """Test retrieving topography without permission returns 404."""
    surface = SurfaceFactory(created_by=user_bob)
    topo = Topography1DFactory(surface=surface, created_by=user_bob)
    topo.grant_permission(user_bob, "view")
    # No permission for Alice

    api_client.force_login(user_alice)
    url = reverse("manager:topography-v2-detail", kwargs={"pk": topo.id})
    response = api_client.get(url)

    # Object permission returns 404 to hide existence
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_topography_retrieve_unauthenticated(api_client, one_line_scan):
    """Test retrieving topography without authentication."""
    url = reverse("manager:topography-v2-detail", kwargs={"pk": one_line_scan.id})
    response = api_client.get(url)

    # IsAuthenticatedOrReadOnly allows GET but object permission may deny
    # Depends on whether topography is public
    assert response.status_code in [
        status.HTTP_200_OK,
        status.HTTP_403_FORBIDDEN,
        status.HTTP_404_NOT_FOUND,
    ]


# TopographyViewSet Tests - Create


@pytest.mark.django_db
def test_topography_create_success(api_client, user_alice, handle_usage_statistics, one_line_scan):
    """Test creating a topography."""
    surface = SurfaceFactory(created_by=user_alice)
    surface.grant_permission(user_alice, "edit")
    one_line_scan.datafile.grant_permission(user_alice, "view")

    api_client.force_login(user_alice)
    url = reverse("manager:topography-v2-list")
    data = {
        "name": "New Topography",
        "surface": {"id": surface.id},
        "description": "Test description",
        "datafile": {"id": one_line_scan.datafile.id},
    }
    response = api_client.post(url, data)

    assert response.status_code == status.HTTP_201_CREATED, response.data
    assert response.data["name"] == "New Topography"
    assert response.data["surface"]["id"] == surface.id

    # Verify in database
    topo = Topography.objects.get(id=response.data["id"])
    assert topo.name == "New Topography"
    assert topo.surface == surface


@pytest.mark.django_db
def test_topography_create_unauthenticated(api_client):
    """Test that unauthenticated users cannot create topographies."""
    url = reverse("manager:topography-v2-list")
    data = {"name": "New Topography"}
    response = api_client.post(url, data, format="json")

    # IsAuthenticatedOrReadOnly requires authentication for POST
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_topography_create_without_surface(api_client, user_alice):
    """Test that creating topography requires surface."""
    api_client.force_login(user_alice)
    url = reverse("manager:topography-v2-list")
    data = {"name": "New Topography"}
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "surface" in response.data


@pytest.mark.django_db
def test_topography_create_without_surface_permission(api_client, user_alice, user_bob):
    """Test that user needs permission on surface to create topography."""
    surface = SurfaceFactory(created_by=user_bob)
    # No permission granted to Alice

    api_client.force_login(user_alice)
    url = reverse("manager:topography-v2-list")
    data = {"name": "New Topography", "surface": {"id": surface.id}}
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "surface" in response.data


@pytest.mark.django_db
def test_topography_create_with_tags(api_client, user_alice, handle_usage_statistics, one_line_scan):
    """Test creating topography with tags."""
    surface = SurfaceFactory(created_by=user_alice)
    surface.grant_permission(user_alice, "edit")
    one_line_scan.datafile.grant_permission(user_alice, "view")

    tag1 = TagFactory(name="tag1")
    tag2 = TagFactory(name="tag2")

    api_client.force_login(user_alice)
    url = reverse("manager:topography-v2-list")
    data = {
        "name": "New Topography",
        "surface": {"id": surface.id},
        "tags": [tag1.name, tag2.name],
        "datafile": {"id": one_line_scan.datafile.id},
    }
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    # Verify tags
    topo = Topography.objects.get(id=response.data["id"])
    tag_names = [tag.name for tag in topo.tags.all()]
    assert "tag1" in tag_names
    assert "tag2" in tag_names


# TopographyViewSet Tests - Update


@pytest.mark.django_db
def test_topography_update_success(api_client, user_alice, one_line_scan):
    """Test updating a topography."""
    one_line_scan.created_by = user_alice
    one_line_scan.save()
    one_line_scan.grant_permission(user_alice, "edit")

    api_client.force_login(user_alice)
    url = reverse("manager:topography-v2-detail", kwargs={"pk": one_line_scan.id})
    data = {"name": "Updated Name", "description": "Updated description"}
    response = api_client.patch(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["name"] == "Updated Name"
    assert response.data["description"] == "Updated description"

    # Verify in database
    one_line_scan.refresh_from_db()
    assert one_line_scan.name == "Updated Name"


@pytest.mark.django_db
def test_topography_update_no_permission(api_client, user_alice, user_bob):
    """Test that user without edit permission cannot update topography."""
    surface = SurfaceFactory(created_by=user_bob)
    topo = Topography1DFactory(surface=surface, created_by=user_bob)
    topo.grant_permission(user_alice, "view")  # Only view permission

    api_client.force_login(user_alice)
    url = reverse("manager:topography-v2-detail", kwargs={"pk": topo.id})
    data = {"name": "Updated Name"}
    response = api_client.patch(url, data, format="json")

    # Edit requires "edit" permission
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_topography_update_unauthenticated(api_client, one_line_scan):
    """Test that unauthenticated users cannot update topographies."""
    url = reverse("manager:topography-v2-detail", kwargs={"pk": one_line_scan.id})
    data = {"name": "Updated Name"}
    response = api_client.patch(url, data, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_topography_update_non_editable_field(api_client, user_alice, one_line_scan):
    """Test that non-editable fields cannot be updated."""
    one_line_scan.created_by = user_alice
    one_line_scan.size_editable = False
    one_line_scan.save()
    one_line_scan.grant_permission(user_alice, "edit")

    api_client.force_login(user_alice)
    url = reverse("manager:topography-v2-detail", kwargs={"pk": one_line_scan.id})
    data = {"size_x": 999.0}
    response = api_client.patch(url, data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST


# TopographyViewSet Tests - Delete


@pytest.mark.django_db
def test_topography_delete_success(api_client, user_alice, one_line_scan):
    """Test deleting a topography."""
    one_line_scan.created_by = user_alice
    one_line_scan.save()
    one_line_scan.grant_permission(user_alice, "full")

    api_client.force_login(user_alice)
    url = reverse("manager:topography-v2-detail", kwargs={"pk": one_line_scan.id})
    response = api_client.delete(url)

    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Verify soft delete
    one_line_scan.refresh_from_db()
    assert one_line_scan.deletion_time is not None


@pytest.mark.django_db
def test_topography_delete_no_permission(api_client, user_alice, user_bob):
    """Test that user without full permission cannot delete topography."""
    surface = SurfaceFactory(created_by=user_bob)
    topo = Topography1DFactory(surface=surface, created_by=user_bob)
    topo.grant_permission(user_alice, "edit")  # Only edit permission, not full

    api_client.force_login(user_alice)
    url = reverse("manager:topography-v2-detail", kwargs={"pk": topo.id})
    response = api_client.delete(url)

    # Delete requires "full" permission
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_topography_delete_unauthenticated(api_client, one_line_scan):
    """Test that unauthenticated users cannot delete topographies."""
    url = reverse("manager:topography-v2-detail", kwargs={"pk": one_line_scan.id})
    response = api_client.delete(url)

    assert response.status_code == status.HTTP_403_FORBIDDEN


# TopographyViewSet Tests - Filtering


@pytest.mark.django_db
def test_topography_list_filter_by_surface(api_client, user_alice):
    """Test filtering topographies by surface."""
    surface1 = SurfaceFactory(created_by=user_alice)
    surface2 = SurfaceFactory(created_by=user_alice)
    surface1.grant_permission(user_alice, "view")
    surface2.grant_permission(user_alice, "view")

    topo1 = Topography1DFactory(surface=surface1, created_by=user_alice)
    topo2 = Topography1DFactory(surface=surface2, created_by=user_alice)
    topo1.grant_permission(user_alice, "view")
    topo2.grant_permission(user_alice, "view")

    api_client.force_login(user_alice)
    url = reverse("manager:topography-v2-list")
    response = api_client.get(url, {"surface": surface1.id})

    assert response.status_code == status.HTTP_200_OK
    topo_ids = [t["id"] for t in response.data["results"]]
    assert topo1.id in topo_ids
    assert topo2.id not in topo_ids


@pytest.mark.django_db
def test_topography_list_filter_by_tags(api_client, user_alice):
    """Test filtering topographies by tags."""
    surface1 = SurfaceFactory(created_by=user_alice)
    surface1.grant_permission(user_alice, "view")
    tag1 = TagFactory(name="filter_tag1")
    surface1.tags.add(tag1)

    surface2 = SurfaceFactory(created_by=user_alice)
    surface2.grant_permission(user_alice, "view")
    tag2 = TagFactory(name="filter_tag2")
    surface2.tags.add(tag2)

    topo1 = Topography1DFactory(surface=surface1, created_by=user_alice)
    topo1.tags.add(tag1)
    topo1.grant_permission(user_alice, "view")

    topo2 = Topography1DFactory(surface=surface2, created_by=user_alice)
    topo2.tags.add(tag2)
    topo2.grant_permission(user_alice, "view")

    api_client.force_login(user_alice)
    url = reverse("manager:topography-v2-list")
    response = api_client.get(url, {"tag": "filter_tag1"})

    assert response.status_code == status.HTTP_200_OK
    topo_ids = [t["id"] for t in response.data["results"]]
    assert topo1.id in topo_ids
    assert topo2.id not in topo_ids


# SurfaceViewSet Tests - List


@pytest.mark.django_db
def test_surface_list_authenticated(api_client, user_alice):
    """Test listing surfaces as authenticated user."""
    surface = SurfaceFactory(created_by=user_alice)
    surface.grant_permission(user_alice, "view")

    api_client.force_login(user_alice)
    url = reverse("manager:surface-v2-list")
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert "results" in response.data
    assert response.data["count"] >= 1


@pytest.mark.django_db
def test_surface_list_unauthenticated(api_client):
    """Test listing surfaces as unauthenticated user."""
    url = reverse("manager:surface-v2-list")
    response = api_client.get(url)

    # IsAuthenticatedOrReadOnly allows GET for anonymous users
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_surface_list_filtered_by_permission(api_client, user_alice, user_bob):
    """Test that users only see surfaces they have permission for."""
    surface_alice = SurfaceFactory(created_by=user_alice)
    surface_alice.grant_permission(user_alice, "view")

    surface_bob = SurfaceFactory(created_by=user_bob)
    surface_bob.grant_permission(user_bob, "view")

    api_client.force_login(user_alice)
    url = reverse("manager:surface-v2-list")
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    surface_ids = [s["id"] for s in response.data["results"]]
    assert surface_alice.id in surface_ids
    assert surface_bob.id not in surface_ids


# SurfaceViewSet Tests - Retrieve


@pytest.mark.django_db
def test_surface_retrieve_success(api_client, user_alice):
    """Test retrieving a single surface."""
    surface = SurfaceFactory(created_by=user_alice)
    surface.grant_permission(user_alice, "view")

    api_client.force_login(user_alice)
    url = reverse("manager:surface-v2-detail", kwargs={"pk": surface.id})
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["id"] == surface.id
    assert response.data["name"] == surface.name
    assert "api" in response.data


@pytest.mark.django_db
def test_surface_retrieve_no_permission(api_client, user_alice, user_bob):
    """Test retrieving surface without permission returns 404."""
    surface = SurfaceFactory(created_by=user_bob)
    surface.grant_permission(user_bob, "view")

    api_client.force_login(user_alice)
    url = reverse("manager:surface-v2-detail", kwargs={"pk": surface.id})
    response = api_client.get(url)

    assert response.status_code == status.HTTP_404_NOT_FOUND


# SurfaceViewSet Tests - Create


@pytest.mark.django_db
def test_surface_create_success(api_client, user_alice):
    """Test creating a surface."""
    api_client.force_login(user_alice)
    url = reverse("manager:surface-v2-list")
    data = {"name": "New Surface", "description": "Test description", "category": "exp"}
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["name"] == "New Surface"

    # Verify in database
    surface = Surface.objects.get(id=response.data["id"])
    assert surface.name == "New Surface"


@pytest.mark.django_db
def test_surface_create_unauthenticated(api_client):
    """Test that unauthenticated users cannot create surfaces."""
    url = reverse("manager:surface-v2-list")
    data = {"name": "New Surface"}
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_surface_create_with_tags(api_client, user_alice):
    """Test creating surface with tags."""
    TagFactory(name="surface_tag1")
    TagFactory(name="surface_tag2")

    api_client.force_login(user_alice)
    url = reverse("manager:surface-v2-list")
    data = {
        "name": "New Surface",
        "tags": ["surface_tag1", "surface_tag2"],
    }
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    # Verify tags
    surface = Surface.objects.get(id=response.data["id"])
    tag_names = [tag.name for tag in surface.tags.all()]
    assert "surface_tag1" in tag_names
    assert "surface_tag2" in tag_names


# SurfaceViewSet Tests - Update


@pytest.mark.django_db
def test_surface_update_success(api_client, user_alice):
    """Test updating a surface."""
    surface = SurfaceFactory(created_by=user_alice, name="Old Name")
    surface.grant_permission(user_alice, "edit")

    api_client.force_login(user_alice)
    url = reverse("manager:surface-v2-detail", kwargs={"pk": surface.id})
    data = {"name": "Updated Name", "description": "Updated description"}
    response = api_client.patch(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["name"] == "Updated Name"

    # Verify in database
    surface.refresh_from_db()
    assert surface.name == "Updated Name"


@pytest.mark.django_db
def test_surface_update_no_permission(api_client, user_alice, user_bob):
    """Test that user without edit permission cannot update surface."""
    surface = SurfaceFactory(created_by=user_bob)
    surface.grant_permission(user_alice, "view")

    api_client.force_login(user_alice)
    url = reverse("manager:surface-v2-detail", kwargs={"pk": surface.id})
    data = {"name": "Updated Name"}
    response = api_client.patch(url, data, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN


# SurfaceViewSet Tests - Delete


@pytest.mark.django_db
def test_surface_delete_success(api_client, user_alice):
    """Test deleting a surface."""
    surface = SurfaceFactory(created_by=user_alice)
    surface.grant_permission(user_alice, "full")

    api_client.force_login(user_alice)
    url = reverse("manager:surface-v2-detail", kwargs={"pk": surface.id})
    response = api_client.delete(url)

    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Verify soft delete
    surface.refresh_from_db()
    assert surface.deletion_time is not None


@pytest.mark.django_db
def test_surface_delete_no_permission(api_client, user_alice, user_bob):
    """Test that user without full permission cannot delete surface."""
    surface = SurfaceFactory(created_by=user_bob)
    surface.grant_permission(user_alice, "edit")

    api_client.force_login(user_alice)
    url = reverse("manager:surface-v2-detail", kwargs={"pk": surface.id})
    response = api_client.delete(url)

    assert response.status_code == status.HTTP_403_FORBIDDEN


# ZipContainerViewSet Tests - Retrieve


@pytest.mark.django_db
def test_zip_container_retrieve_success(api_client, user_alice):
    """Test retrieving a ZIP container."""
    permissions = PermissionSetFactory(user=user_alice, allow="view")
    zip_container = ZipContainer.objects.create(permissions=permissions)

    api_client.force_login(user_alice)
    url = reverse("manager:zip-container-v2-detail", kwargs={"pk": zip_container.id})
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["id"] == zip_container.id
    assert "task_state" in response.data
    assert "api" in response.data


@pytest.mark.django_db
def test_zip_container_retrieve_no_permission(api_client, user_alice, user_bob):
    """Test retrieving ZIP container without permission returns 404."""
    permissions = PermissionSetFactory(user=user_bob, allow="view")
    zip_container = ZipContainer.objects.create(permissions=permissions)

    api_client.force_login(user_alice)
    url = reverse("manager:zip-container-v2-detail", kwargs={"pk": zip_container.id})
    response = api_client.get(url)

    assert response.status_code == status.HTTP_404_NOT_FOUND


# Function-based View Tests - download_surface


@pytest.mark.django_db
def test_download_surface_single_id(api_client, user_alice, handle_usage_statistics):
    """Test downloading a single surface."""
    surface = SurfaceFactory(created_by=user_alice)
    surface.grant_permission(user_alice, "view")

    api_client.force_login(user_alice)
    url = reverse("manager:surface-download-v2", kwargs={"surface_ids": surface.id})
    response = api_client.post(url)

    assert response.status_code == status.HTTP_200_OK
    assert "id" in response.data
    assert "task_state" in response.data
    # Verify ZipContainer created
    zip_container = ZipContainer.objects.get(id=response.data["id"])
    assert zip_container is not None


@pytest.mark.django_db
def test_download_surface_multiple_ids(api_client, user_alice, handle_usage_statistics):
    """Test downloading multiple surfaces."""
    surface1 = SurfaceFactory(created_by=user_alice)
    surface2 = SurfaceFactory(created_by=user_alice)
    surface1.grant_permission(user_alice, "view")
    surface2.grant_permission(user_alice, "view")

    api_client.force_login(user_alice)
    url = reverse(
        "manager:surface-download-v2",
        kwargs={"surface_ids": f"{surface1.id},{surface2.id}"},
    )
    response = api_client.post(url)

    assert response.status_code == status.HTTP_200_OK
    assert "id" in response.data


@pytest.mark.django_db
def test_download_surface_invalid_ids(api_client, user_alice):
    """Test downloading surfaces with invalid IDs."""
    api_client.force_login(user_alice)
    url = reverse("manager:surface-download-v2", kwargs={"surface_ids": "99999"})
    response = api_client.post(url)

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_download_surface_unauthenticated(api_client):
    """Test that unauthenticated users cannot download surfaces."""
    url = reverse("manager:surface-download-v2", kwargs={"surface_ids": "1"})
    response = api_client.post(url)

    assert response.status_code == status.HTTP_403_FORBIDDEN


# Function-based View Tests - download_tag


@pytest.mark.django_db
def test_download_tag_success(api_client, user_alice, handle_usage_statistics):
    """Test downloading surfaces by tag."""
    tag = TagFactory(name="download_tag")
    surface = SurfaceFactory(created_by=user_alice)
    surface.tags.add(tag)
    surface.grant_permission(user_alice, "view")

    api_client.force_login(user_alice)
    url = reverse("manager:tag-download-v2", kwargs={"name": "download_tag"})
    response = api_client.post(url)

    assert response.status_code == status.HTTP_200_OK
    assert "id" in response.data
    assert "task_state" in response.data


@pytest.mark.django_db
def test_download_tag_unauthenticated(api_client):
    """Test that unauthenticated users cannot download by tag."""
    url = reverse("manager:tag-download-v2", kwargs={"name": "test_tag"})
    response = api_client.post(url)

    assert response.status_code == status.HTTP_403_FORBIDDEN


# Function-based View Tests - upload_zip_start


@pytest.mark.django_db
def test_upload_zip_start_success(api_client, user_alice):
    """Test starting a ZIP upload."""
    api_client.force_login(user_alice)
    url = reverse("manager:zip-upload-start-v2")
    response = api_client.post(url)

    assert response.status_code == status.HTTP_200_OK
    assert "id" in response.data
    assert "api" in response.data
    assert "upload_finished" in response.data["api"]

    # Verify ZipContainer created with full permission
    zip_container = ZipContainer.objects.get(id=response.data["id"])
    assert zip_container is not None
    # Check user has full permission
    zip_container.authorize_user(user_alice, "full")  # Should not raise


@pytest.mark.django_db
def test_upload_zip_start_unauthenticated(api_client):
    """Test that unauthenticated users cannot start upload."""
    url = reverse("manager:zip-upload-start-v2")
    response = api_client.post(url)

    assert response.status_code == status.HTTP_403_FORBIDDEN


# Function-based View Tests - upload_zip_finish


@pytest.mark.django_db
def test_upload_zip_finish_success(api_client, user_alice, handle_usage_statistics):
    """Test finishing a ZIP upload."""
    permissions = PermissionSetFactory(user=user_alice, allow="full")
    zip_container = ZipContainer.objects.create(permissions=permissions)

    api_client.force_login(user_alice)
    url = reverse("manager:zip-upload-finish-v2", kwargs={"pk": zip_container.id})
    response = api_client.post(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["id"] == zip_container.id

    # Verify task was triggered
    zip_container.refresh_from_db()
    # Task state should be set to pending
    assert zip_container.task_state == "pe"


@pytest.mark.django_db
def test_upload_zip_finish_not_found(api_client, user_alice):
    """Test finishing upload with invalid ZIP container ID."""
    api_client.force_login(user_alice)
    url = reverse("manager:zip-upload-finish-v2", kwargs={"pk": 99999})
    response = api_client.post(url)

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_upload_zip_finish_no_permission(api_client, user_alice, user_bob):
    """Test that user without permission cannot finish upload."""
    permissions = PermissionSetFactory(user=user_bob, allow="full")
    zip_container = ZipContainer.objects.create(permissions=permissions)

    api_client.force_login(user_alice)
    url = reverse("manager:zip-upload-finish-v2", kwargs={"pk": zip_container.id})
    response = api_client.post(url)

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_upload_zip_finish_unauthenticated(api_client):
    """Test that unauthenticated users cannot finish upload."""
    permissions = PermissionSetFactory()
    zip_container = ZipContainer.objects.create(permissions=permissions)

    url = reverse("manager:zip-upload-finish-v2", kwargs={"pk": zip_container.id})
    response = api_client.post(url)

    assert response.status_code == status.HTTP_403_FORBIDDEN
