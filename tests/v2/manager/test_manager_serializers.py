"""Tests for topobank.manager.v2 serializers."""

import pytest

from topobank.manager.models import Manifest
from topobank.manager.v2.serializers import (
    SurfaceV2Serializer,
    TopographyV2CreateSerializer,
    TopographyV2Serializer,
    ZipContainerV2Serializer,
)
from topobank.manager.zip_model import ZipContainer
from topobank.testing.factories import (
    PermissionSetFactory,
    PropertyFactory,
    SurfaceFactory,
    TagFactory,
)

# TopographyV2Serializer Tests


@pytest.mark.django_db
def test_topography_v2_serializer_read_only_fields(api_rf, user_alice, one_line_scan):
    """Test that read-only fields are present in serialized output."""
    one_line_scan.grant_permission(user_alice, "view")
    request = api_rf.get("/")
    request.query_params = {}
    request.user = user_alice

    serializer = TopographyV2Serializer(
        instance=one_line_scan, context={"request": request}
    )
    data = serializer.data

    # Check read-only fields are present
    assert "id" in data
    assert "url" in data
    assert "api" in data
    assert "permissions" in data
    assert "created_by" in data
    assert "updated_by" in data
    assert "owned_by" in data
    assert "created_at" in data
    assert "updated_at" in data
    assert "task_state" in data
    assert "task_duration" in data
    assert "task_error" in data
    assert "task_progress" in data
    assert "datafile" in data
    assert "squeezed_datafile" in data
    assert "thumbnail" in data
    assert "deepzoom" in data
    assert "datafile_format" in data
    assert "channel_names" in data
    assert "data_source" in data
    assert "size_editable" in data
    assert "unit_editable" in data
    assert "height_scale_editable" in data
    assert "has_undefined_data" in data
    assert "is_periodic_editable" in data
    assert "is_metadata_complete" in data


@pytest.mark.django_db
def test_topography_v2_serializer_editable_fields(api_rf, user_alice, one_line_scan):
    """Test that editable fields are present in serialized output."""
    one_line_scan.grant_permission(user_alice, "view")
    request = api_rf.get("/")
    request.query_params = {}
    request.user = user_alice

    serializer = TopographyV2Serializer(
        instance=one_line_scan, context={"request": request}
    )
    data = serializer.data

    # Check editable fields are present
    assert "name" in data
    assert "description" in data
    assert "measurement_date" in data
    assert "size_x" in data
    assert "size_y" in data
    assert "unit" in data
    assert "height_scale" in data
    assert "fill_undefined_data_mode" in data
    assert "detrend_mode" in data
    assert "resolution_x" in data
    assert "resolution_y" in data
    assert "bandwidth_lower" in data
    assert "bandwidth_upper" in data
    assert "short_reliability_cutoff" in data
    assert "is_periodic" in data
    assert "instrument_name" in data
    assert "instrument_type" in data
    assert "instrument_parameters" in data
    assert "tags" in data
    assert "surface" in data
    assert "attachments" in data


@pytest.mark.django_db
def test_topography_v2_serializer_api_field(api_rf, user_alice, one_line_scan):
    """Test that api field contains correct URLs."""
    one_line_scan.grant_permission(user_alice, "view")
    request = api_rf.get("/")
    request.query_params = {}
    request.user = user_alice

    serializer = TopographyV2Serializer(
        instance=one_line_scan, context={"request": request}
    )
    data = serializer.data

    assert "api" in data
    assert "force_inspect" in data["api"]
    # NOTE: Force-inspect is still v1
    assert f"/api/topography/{one_line_scan.id}/force-inspect/" in data["api"]["force_inspect"]


@pytest.mark.django_db
def test_topography_v2_serializer_tags_handling(api_rf, user_alice, one_line_scan):
    """Test that tags are properly serialized and deserialized."""
    tag1 = TagFactory(name="tag1")
    tag2 = TagFactory(name="tag2")
    one_line_scan.tags.add(tag1, tag2)
    one_line_scan.grant_permission(user_alice, "view")

    request = api_rf.get("/")
    request.query_params = {}
    request.user = user_alice

    serializer = TopographyV2Serializer(
        instance=one_line_scan, context={"request": request}
    )
    data = serializer.data

    assert "tags" in data
    assert len(data["tags"]) == 2
    assert "tag1" in data['tags']
    assert "tag2" in data['tags']


@pytest.mark.django_db
def test_topography_v2_serializer_validate_non_editable_size(
    api_rf, user_alice, one_line_scan
):
    """Test that size fields cannot be edited when not editable."""
    one_line_scan.grant_permission(user_alice, "edit")
    # Assume datafile provides size, making it non-editable
    one_line_scan.size_editable = False
    one_line_scan.save()

    request = api_rf.patch("/")
    request.query_params = {}
    request.user = user_alice

    serializer = TopographyV2Serializer(
        instance=one_line_scan,
        data={"size_x": 100.0, "size_y": 100.0},
        partial=True,
        context={"request": request},
    )

    assert not serializer.is_valid()
    assert "non_field_errors" in serializer.errors or "size_x" in str(serializer.errors)


@pytest.mark.django_db
def test_topography_v2_serializer_validate_non_editable_unit(
    api_rf, user_alice, one_line_scan
):
    """Test that unit field cannot be edited when not editable."""
    one_line_scan.grant_permission(user_alice, "edit")
    one_line_scan.unit_editable = False
    one_line_scan.save()

    request = api_rf.patch("/")
    request.query_params = {}
    request.user = user_alice

    serializer = TopographyV2Serializer(
        instance=one_line_scan,
        data={"unit": "mm"},
        partial=True,
        context={"request": request},
    )

    assert not serializer.is_valid()


@pytest.mark.django_db
def test_topography_v2_serializer_validate_non_editable_height_scale(
    api_rf, user_alice, one_line_scan
):
    """Test that height_scale field cannot be edited when not editable."""
    one_line_scan.grant_permission(user_alice, "edit")
    one_line_scan.height_scale_editable = False
    one_line_scan.save()

    request = api_rf.patch("/")
    request.query_params = {}
    request.user = user_alice

    serializer = TopographyV2Serializer(
        instance=one_line_scan,
        data={"height_scale": 2.0},
        partial=True,
        context={"request": request},
    )

    assert not serializer.is_valid()


@pytest.mark.django_db
def test_topography_v2_serializer_validate_non_editable_is_periodic(
    api_rf, user_alice, one_line_scan
):
    """Test that is_periodic field cannot be edited when not editable."""
    one_line_scan.grant_permission(user_alice, "edit")
    one_line_scan.is_periodic_editable = False
    one_line_scan.save()

    request = api_rf.patch("/")
    request.query_params = {}
    request.user = user_alice

    serializer = TopographyV2Serializer(
        instance=one_line_scan,
        data={"is_periodic": True},
        partial=True,
        context={"request": request},
    )

    assert not serializer.is_valid()


@pytest.mark.django_db
def test_topography_v2_serializer_editable_fields_success(
    api_rf, user_alice, one_line_scan
):
    """Test that editable fields can be updated when allowed."""
    one_line_scan.grant_permission(user_alice, "edit")
    one_line_scan.size_editable = True
    one_line_scan.save()

    request = api_rf.patch("/")
    request.query_params = {}
    request.user = user_alice

    serializer = TopographyV2Serializer(
        instance=one_line_scan,
        data={"size_x": 200.0, "name": "Updated Name"},
        partial=True,
        context={"request": request},
    )

    assert serializer.is_valid()
    updated = serializer.save()
    assert updated.size_x == 200.0
    assert updated.name == "Updated Name"


@pytest.mark.django_db
def test_topography_v2_serializer_url_field(api_rf, user_alice, one_line_scan):
    """Test that url field generates correct hyperlink."""
    one_line_scan.grant_permission(user_alice, "view")
    request = api_rf.get("/")
    request.query_params = {}
    request.user = user_alice

    serializer = TopographyV2Serializer(
        instance=one_line_scan, context={"request": request}
    )
    data = serializer.data

    assert "url" in data
    assert f"/v2/topography/{one_line_scan.id}/" in data["url"]


@pytest.mark.django_db
def test_topography_v2_serializer_permissions_field(api_rf, user_alice, one_line_scan):
    """Test that permissions field is serialized correctly."""
    one_line_scan.grant_permission(user_alice, "view")
    request = api_rf.get("/")
    request.query_params = {}
    request.user = user_alice

    serializer = TopographyV2Serializer(
        instance=one_line_scan, context={"request": request}
    )
    data = serializer.data

    assert "permissions" in data
    assert data["permissions"] is not None


@pytest.mark.django_db
def test_topography_v2_serializer_manifest_fields(api_rf, user_alice, one_line_scan):
    """Test that manifest fields (datafile, thumbnail, etc.) are serialized."""
    one_line_scan.grant_permission(user_alice, "view")
    request = api_rf.get("/")
    request.query_params = {}
    request.user = user_alice

    serializer = TopographyV2Serializer(
        instance=one_line_scan, context={"request": request}
    )
    data = serializer.data

    # These may be None but should be present
    assert "datafile" in data
    assert "squeezed_datafile" in data
    assert "thumbnail" in data


@pytest.mark.django_db
def test_topography_v2_serializer_user_fields(api_rf, user_alice, one_line_scan):
    """Test that user fields (created_by, updated_by) are serialized."""
    one_line_scan.created_by = user_alice
    one_line_scan.updated_by = user_alice
    one_line_scan.save()
    one_line_scan.grant_permission(user_alice, "view")

    request = api_rf.get("/")
    request.query_params = {}
    request.user = user_alice

    serializer = TopographyV2Serializer(
        instance=one_line_scan, context={"request": request}
    )
    data = serializer.data

    assert "created_by" in data
    assert "updated_by" in data
    if data["created_by"]:
        assert data["created_by"]["id"] == user_alice.id
    if data["updated_by"]:
        assert data["updated_by"]["id"] == user_alice.id


# TopographyV2CreateSerializer Tests


@pytest.mark.django_db
def test_topography_v2_create_serializer_required_fields(api_rf, user_alice, one_line_scan):
    """Test that surface field is required for creation."""
    surface = SurfaceFactory(created_by=user_alice)
    surface.grant_permission(user_alice, "edit")
    manifest = one_line_scan.datafile
    manifest.grant_permission(user_alice, "view")

    request = api_rf.post("/")
    request.query_params = {}
    request.user = user_alice

    # Without surface
    serializer = TopographyV2CreateSerializer(
        data={"name": "Test Topo", "datafile": {"id": manifest.id}}, context={"request": request}
    )
    assert not serializer.is_valid()
    assert "surface" in serializer.errors

    # Without name
    serializer = TopographyV2CreateSerializer(
        data={
            "surface": {"id": surface.id},
            "datafile": {"id": manifest.id}
        },
        context={"request": request}
    )
    assert not serializer.is_valid()
    assert "name" in serializer.errors

    # With both
    serializer = TopographyV2CreateSerializer(
        data={
            "name": "Test Topo",
            "surface": {"id": surface.id},
            "datafile": {"id": manifest.id}
        },
        context={"request": request}
    )
    assert serializer.is_valid()


@pytest.mark.django_db
def test_topography_v2_create_serializer_surface_permission_check(api_rf, user_alice, user_bob):
    """Test that user needs permission to assign surface."""
    surface = SurfaceFactory(created_by=user_bob)
    # Don't grant permission to user_alice

    request = api_rf.post("/")
    request.query_params = {}
    request.user = user_alice

    serializer = TopographyV2CreateSerializer(
        data={"name": "Test Topo", "surface": {"id": surface.id}}, context={"request": request}
    )
    assert not serializer.is_valid()
    assert "surface" in serializer.errors


# SurfaceV2Serializer Tests


@pytest.mark.django_db
def test_surface_v2_serializer_read_only_fields(api_rf, user_alice):
    """Test that read-only fields are present in serialized output."""
    surface = SurfaceFactory(created_by=user_alice)
    surface.grant_permission(user_alice, "view")

    request = api_rf.get("/")
    request.query_params = {}
    request.user = user_alice

    serializer = SurfaceV2Serializer(instance=surface, context={"request": request})
    data = serializer.data

    # Check read-only fields
    assert "id" in data
    assert "url" in data
    assert "api" in data
    assert "permissions" in data
    assert "created_by" in data
    assert "updated_by" in data
    assert "owned_by" in data
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.django_db
def test_surface_v2_serializer_editable_fields(api_rf, user_alice):
    """Test that editable fields are present in serialized output."""
    surface = SurfaceFactory(created_by=user_alice)
    surface.grant_permission(user_alice, "view")

    request = api_rf.get("/")
    request.query_params = {}
    request.user = user_alice

    serializer = SurfaceV2Serializer(instance=surface, context={"request": request})
    data = serializer.data

    # Check editable fields
    assert "name" in data
    assert "category" in data
    assert "description" in data
    assert "tags" in data
    assert "properties" in data
    assert "attachments" in data


@pytest.mark.django_db
def test_surface_v2_serializer_api_field(api_rf, user_alice):
    """Test that api field contains correct URLs."""
    surface = SurfaceFactory(created_by=user_alice)
    surface.grant_permission(user_alice, "view")

    request = api_rf.get("/")
    request.query_params = {}
    request.user = user_alice

    serializer = SurfaceV2Serializer(instance=surface, context={"request": request})
    data = serializer.data

    assert "api" in data
    assert "async_download" in data["api"]
    assert "topographies" in data["api"]
    assert f"/v2/download-surface/{surface.id}/" in data["api"]["async_download"]
    assert "/v2/topography/" in data["api"]["topographies"]


@pytest.mark.django_db
def test_surface_v2_serializer_url_field(api_rf, user_alice):
    """Test that url field generates correct hyperlink."""
    surface = SurfaceFactory(created_by=user_alice)
    surface.grant_permission(user_alice, "view")

    request = api_rf.get("/")
    request.query_params = {}
    request.user = user_alice

    serializer = SurfaceV2Serializer(instance=surface, context={"request": request})
    data = serializer.data

    assert "url" in data
    assert f"/v2/surface/{surface.id}/" in data["url"]


@pytest.mark.django_db
def test_surface_v2_serializer_tags_handling(api_rf, user_alice):
    """Test that tags are properly serialized."""
    surface = SurfaceFactory(created_by=user_alice)
    tag1 = TagFactory(name="surface_tag1")
    tag2 = TagFactory(name="surface_tag2")
    surface.tags.add(tag1, tag2)
    surface.grant_permission(user_alice, "view")

    request = api_rf.get("/")
    request.query_params = {}
    request.user = user_alice

    serializer = SurfaceV2Serializer(instance=surface, context={"request": request})
    data = serializer.data

    assert "tags" in data
    assert len(data["tags"]) == 2
    assert "surface_tag1" in data['tags']
    assert "surface_tag2" in data['tags']


@pytest.mark.django_db
def test_surface_v2_serializer_properties_field(api_rf, user_alice):
    """Test that properties field is serialized correctly."""
    surface = SurfaceFactory(created_by=user_alice)
    surface.grant_permission(user_alice, "view")

    PropertyFactory.create(name="key1", value="value1", surface=surface, permissions=surface.permissions)
    PropertyFactory.create(name="key2", value=123, surface=surface, permissions=surface.permissions)

    request = api_rf.get("/")
    request.query_params = {}
    request.user = user_alice

    serializer = SurfaceV2Serializer(instance=surface, context={"request": request})
    data = serializer.data

    assert "properties" in data
    assert "key1" in data["properties"]
    assert data["properties"]["key1"]["value"] == "value1"

    assert "key2" in data["properties"]
    assert data["properties"]["key2"]["value"] == 123


@pytest.mark.django_db
def test_surface_v2_serializer_permissions_field(api_rf, user_alice):
    """Test that permissions field is serialized correctly."""
    surface = SurfaceFactory(created_by=user_alice)

    request = api_rf.get("/")
    request.query_params = {}
    request.user = user_alice

    serializer = SurfaceV2Serializer(instance=surface, context={"request": request})
    data = serializer.data

    assert "permissions" in data
    assert data["permissions"] is not None

    assert "allow" in data["permissions"]
    assert data["permissions"]["allow"] == "full"


@pytest.mark.django_db
def test_surface_v2_serializer_create(api_rf, user_alice):
    """Test creating a surface via serializer."""
    request = api_rf.post("/")
    request.query_params = {}
    request.user = user_alice

    data = {
        "name": "New Surface",
        "description": "Test description",
        "category": "exp",
    }

    serializer = SurfaceV2Serializer(data=data, context={"request": request})
    assert serializer.is_valid()
    assert serializer.validated_data['name'] == "New Surface"
    assert serializer.validated_data['description'] == "Test description"
    assert serializer.validated_data['category'] == "exp"


@pytest.mark.django_db
def test_surface_v2_serializer_update(api_rf, user_alice):
    """Test updating a surface via serializer."""
    surface = SurfaceFactory(created_by=user_alice, name="Old Name")
    surface.grant_permission(user_alice, "edit")

    request = api_rf.patch("/")
    request.query_params = {}
    request.user = user_alice

    serializer = SurfaceV2Serializer(
        instance=surface,
        data={"name": "New Name", "description": "Updated description"},
        partial=True,
        context={"request": request},
    )

    assert serializer.is_valid()
    assert serializer.validated_data['name'] == "New Name"
    assert serializer.validated_data['description'] == "Updated description"


# ZipContainerV2Serializer Tests


@pytest.mark.django_db
def test_zip_container_v2_serializer_api_field(api_rf, user_alice):
    """Test that api field contains correct URLs."""
    permissions = PermissionSetFactory(user=user_alice, allow="view")
    zip_container = ZipContainer.objects.create(permissions=permissions)

    request = api_rf.get("/")
    request.query_params = {}
    request.user = user_alice

    serializer = ZipContainerV2Serializer(
        instance=zip_container, context={"request": request}
    )
    data = serializer.data

    assert "api" in data
    assert "upload_finished" in data["api"]
    assert f"/v2/upload-zip/finish/{zip_container.id}/" in data["api"]["upload_finished"]


@pytest.mark.django_db
def test_zip_container_v2_serializer_url_field(api_rf, user_alice):
    """Test that url field generates correct hyperlink."""
    permissions = PermissionSetFactory(user=user_alice, allow="view")
    zip_container = ZipContainer.objects.create(permissions=permissions)

    request = api_rf.get("/")
    request.query_params = {}
    request.user = user_alice

    serializer = ZipContainerV2Serializer(
        instance=zip_container, context={"request": request}
    )
    data = serializer.data

    assert "url" in data
    assert f"/v2/zip-container/{zip_container.id}/" in data["url"]


@pytest.mark.django_db
def test_zip_container_v2_serializer_manifest_field(api_rf, user_alice):
    """Test that manifest field is serialized correctly."""
    permissions = PermissionSetFactory(user=user_alice, allow="view")
    zip_container = ZipContainer.objects.create(permissions=permissions)
    manifest = Manifest.objects.create()
    zip_container.manifest = manifest
    zip_container.save()

    request = api_rf.get("/")
    request.query_params = {}
    request.user = user_alice

    serializer = ZipContainerV2Serializer(
        instance=zip_container, context={"request": request}
    )
    data = serializer.data

    assert "manifest" in data


@pytest.mark.django_db
def test_zip_container_v2_serializer_permissions_field(api_rf, user_alice):
    """Test that permissions field is serialized correctly."""
    permissions = PermissionSetFactory(user=user_alice, allow="view")
    zip_container = ZipContainer.objects.create(permissions=permissions)

    request = api_rf.get("/")
    request.query_params = {}
    request.user = user_alice

    serializer = ZipContainerV2Serializer(
        instance=zip_container, context={"request": request}
    )
    data = serializer.data

    assert "permissions" in data
    assert data["permissions"] is not None
    assert data["permissions"]["allow"] == "view"
