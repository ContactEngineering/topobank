"""
Tests for topobank.supplib.serializers module.

This module tests the custom Django REST Framework serializers and fields
including StrictFieldMixin, DynamicFieldsModelSerializer, PermissionsField,
ModelRelatedField, and specialized fields like UserField, OrganizationField,
SubjectField, ManifestField, and StringOrIntegerField.
"""
import pytest
from django.urls import reverse
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request

from topobank.manager.models import Surface
from topobank.supplib.serializers import (
    DynamicFieldsModelSerializer,
    ManifestField,
    ModelRelatedField,
    OrganizationField,
    PermissionsField,
    StringOrIntegerField,
    SubjectField,
    UserField,
)
from topobank.testing.factories import (
    AnalysisSubjectFactory,
    ManifestFactory,
    SurfaceFactory,
    TagFactory,
    Topography1DFactory,
    UserFactory,
)

# ============================================================================
# Test DynamicFieldsModelSerializer
# ============================================================================


class DynamicTestSerializer(DynamicFieldsModelSerializer):
    """Test serializer for DynamicFieldsModelSerializer."""

    class Meta:
        model = Surface
        fields = ["id", "name", "description", "created_at", "updated_at"]


@pytest.mark.django_db
def test_dynamic_fields_no_filtering(api_rf, user_alice):
    """Test DynamicFieldsModelSerializer returns all fields by default."""

    surface = SurfaceFactory(created_by=user_alice)
    wsgi_request = api_rf.get("/")
    request = Request(wsgi_request)

    serializer = DynamicTestSerializer(surface, context={"request": request})
    data = serializer.data

    # All fields should be present
    assert "id" in data
    assert "name" in data
    assert "description" in data
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.django_db
def test_dynamic_fields_with_fields_filter(api_rf, user_alice):
    """Test DynamicFieldsModelSerializer filters fields based on 'fields' query param."""

    surface = SurfaceFactory(created_by=user_alice)
    wsgi_request = api_rf.get("/?fields=id,name")
    request = Request(wsgi_request)

    serializer = DynamicTestSerializer(surface, context={"request": request})
    data = serializer.data

    # Only specified fields should be present
    assert "id" in data
    assert "name" in data
    assert "description" not in data
    assert "created_at" not in data
    assert "updated_at" not in data


@pytest.mark.django_db
def test_dynamic_fields_with_exclude_filter(api_rf, user_alice):
    """Test DynamicFieldsModelSerializer excludes fields based on 'exclude' query param."""

    surface = SurfaceFactory(created_by=user_alice)
    wsgi_request = api_rf.get("/?exclude=description,created_at")
    request = Request(wsgi_request)

    serializer = DynamicTestSerializer(surface, context={"request": request})
    data = serializer.data

    # Excluded fields should not be present
    assert "id" in data
    assert "name" in data
    assert "updated_at" in data
    assert "description" not in data
    assert "created_at" not in data


@pytest.mark.django_db
def test_dynamic_fields_invalid_field_names_ignored(api_rf, user_alice):
    """Test DynamicFieldsModelSerializer ignores invalid field names."""

    surface = SurfaceFactory(created_by=user_alice)
    wsgi_request = api_rf.get("/?fields=id,name,nonexistent_field")
    request = Request(wsgi_request)

    serializer = DynamicTestSerializer(surface, context={"request": request})
    data = serializer.data

    # Only valid fields should be present
    assert "id" in data
    assert "name" in data
    assert "nonexistent_field" not in data


# ============================================================================
# Test PermissionsField
# ============================================================================


@pytest.mark.django_db
def test_permissions_field_representation(api_rf, user_alice):
    """Test PermissionsField serializes permission set with ID, URL, and allow."""
    surface = SurfaceFactory(created_by=user_alice)
    request = api_rf.get("/")
    request.user = user_alice

    field = PermissionsField(read_only=True)
    field._context = {"request": request}

    data = field.to_representation(surface.permissions)

    assert "id" in data
    assert "url" in data
    assert "allow" in data
    assert data["id"] == surface.permissions.pk
    assert data["allow"] in ["view", "edit", "full"]


@pytest.mark.django_db
def test_permissions_field_custom_view_name(api_rf, user_alice):
    """Test PermissionsField with custom view_name."""
    surface = SurfaceFactory(created_by=user_alice)
    request = api_rf.get("/")
    request.user = user_alice

    field = PermissionsField(
        view_name="authorization:permission-set-v2-detail", read_only=True
    )
    field._context = {"request": request}

    data = field.to_representation(surface.permissions)

    assert "url" in data
    expected_url = reverse(
        "authorization:permission-set-v2-detail", kwargs={"pk": surface.permissions.pk}
    )
    assert expected_url in data["url"]


# ============================================================================
# Test ModelRelatedField
# ============================================================================


@pytest.mark.django_db
def test_model_related_field_to_representation(api_rf, user_alice):
    """Test ModelRelatedField serializes to dict with id and url."""
    user = user_alice
    request = api_rf.get("/")

    field = ModelRelatedField(view_name="users:user-v1-detail", read_only=True)
    field._context = {"request": request}

    data = field.to_representation(user)

    assert "id" in data
    assert "url" in data
    assert data["id"] == user.pk
    assert f"/users/v1/user/{user.pk}/" in data["url"]


@pytest.mark.django_db
def test_model_related_field_with_additional_fields(api_rf, user_alice):
    """Test ModelRelatedField includes additional specified fields."""
    user = user_alice
    request = api_rf.get("/")

    field = ModelRelatedField(
        view_name="users:user-v1-detail", fields=["name", "email"], read_only=True
    )
    field._context = {"request": request}

    data = field.to_representation(user)

    assert "id" in data
    assert "url" in data
    assert "name" in data
    assert "email" in data
    assert data["name"] == user.name
    assert data["email"] == user.email


@pytest.mark.django_db
def test_model_related_field_to_internal_value_by_id(api_rf, user_alice):
    """Test ModelRelatedField deserializes from id."""
    request = api_rf.get("/")

    field = ModelRelatedField(
        view_name="users:user-v1-detail", queryset=user_alice.__class__.objects.all()
    )
    field._context = {"request": request}

    result = field.to_internal_value({"id": user_alice.pk})

    assert result == user_alice


@pytest.mark.django_db
def test_model_related_field_to_internal_value_by_url(api_rf, user_alice):
    """Test ModelRelatedField deserializes from url."""
    request = api_rf.get("/")
    url = reverse("users:user-v1-detail", kwargs={"pk": user_alice.pk})

    field = ModelRelatedField(
        view_name="users:user-v1-detail", queryset=user_alice.__class__.objects.all()
    )
    field._context = {"request": request}

    result = field.to_internal_value({"url": url})

    assert result == user_alice


@pytest.mark.django_db
def test_model_related_field_to_internal_value_both_id_and_url(api_rf, user_alice):
    """Test ModelRelatedField rejects data with both id and url."""
    request = api_rf.get("/")
    url = reverse("users:user-v1-detail", kwargs={"pk": user_alice.pk})

    field = ModelRelatedField(
        view_name="users:user-v1-detail", queryset=user_alice.__class__.objects.all()
    )
    field._context = {"request": request}

    with pytest.raises(ValidationError) as exc_info:
        field.to_internal_value({"id": user_alice.pk, "url": url})

    assert "both present" in str(exc_info.value).lower()


@pytest.mark.django_db
def test_model_related_field_to_internal_value_neither_id_nor_url(api_rf):
    """Test ModelRelatedField rejects data without id or url."""
    request = api_rf.get("/")

    field = ModelRelatedField(
        view_name="users:user-v1-detail", queryset=UserFactory._meta.get_model_class().objects.all()
    )
    field._context = {"request": request}

    with pytest.raises(ValidationError) as exc_info:
        field.to_internal_value({"name": "Some Name"})

    assert "must be present" in str(exc_info.value).lower()


# ============================================================================
# Test UserField
# ============================================================================


@pytest.mark.django_db
def test_user_field_representation(api_rf, user_alice):
    """Test UserField serializes user with id, url, and name."""
    request = api_rf.get("/")

    field = UserField(read_only=True)
    field._context = {"request": request}

    data = field.to_representation(user_alice)

    assert "id" in data
    assert "url" in data
    assert "name" in data
    assert data["id"] == user_alice.pk
    assert data["name"] == user_alice.name
    assert f"/users/v1/user/{user_alice.pk}/" in data["url"]


@pytest.mark.django_db
def test_user_field_deserialization_by_id(api_rf, user_alice):
    """Test UserField deserializes user from id."""
    request = api_rf.get("/")

    field = UserField(queryset=user_alice.__class__.objects.all())
    field._context = {"request": request}

    result = field.to_internal_value({"id": user_alice.pk})

    assert result == user_alice


# ============================================================================
# Test OrganizationField
# ============================================================================


@pytest.mark.django_db
def test_organization_field_representation(api_rf, org_blofield):
    """Test OrganizationField serializes organization with id, url, and name."""
    request = api_rf.get("/")

    field = OrganizationField(read_only=True)
    field._context = {"request": request}

    data = field.to_representation(org_blofield)

    assert "id" in data
    assert "url" in data
    assert "name" in data
    assert data["id"] == org_blofield.pk
    assert data["name"] == org_blofield.name
    assert f"/organizations/v1/organization/{org_blofield.pk}/" in data["url"]


@pytest.mark.django_db
def test_organization_field_deserialization_by_id(api_rf, org_blofield):
    """Test OrganizationField deserializes organization from id."""
    request = api_rf.get("/")

    field = OrganizationField(queryset=org_blofield.__class__.objects.all())
    field._context = {"request": request}

    result = field.to_internal_value({"id": org_blofield.pk})

    assert result == org_blofield


# ============================================================================
# Test SubjectField
# ============================================================================


@pytest.mark.django_db
def test_subject_field_representation_topography(api_rf, user_alice):
    """Test SubjectField serializes topography subject with id, url, name, and type."""
    surface = SurfaceFactory(created_by=user_alice)
    topo = Topography1DFactory(surface=surface)
    request = api_rf.get("/")

    field = SubjectField(read_only=True)
    field._context = {"request": request}

    data = field.to_representation(topo)

    assert "id" in data
    assert "url" in data
    assert "name" in data
    assert "type" in data
    assert data["id"] == topo.pk
    assert data["name"] == topo.name
    assert data["type"] == "topography"
    assert f"/manager/v2/topography/{topo.pk}/" in data["url"]


@pytest.mark.django_db
def test_subject_field_representation_surface(api_rf, user_alice):
    """Test SubjectField serializes surface subject with id, url, name, and type."""
    surface = SurfaceFactory(created_by=user_alice)
    request = api_rf.get("/")

    field = SubjectField(read_only=True)
    field._context = {"request": request}

    data = field.to_representation(surface)

    assert "id" in data
    assert "url" in data
    assert "name" in data
    assert "type" in data
    assert data["id"] == surface.pk
    assert data["name"] == surface.name
    assert data["type"] == "surface"
    assert f"/manager/v2/surface/{surface.pk}/" in data["url"]


@pytest.mark.django_db
def test_subject_field_representation_tag(api_rf, user_alice):
    """Test SubjectField serializes tag subject with id, url, name, and type."""
    tag = TagFactory()
    request = api_rf.get("/")

    field = SubjectField(read_only=True)
    field._context = {"request": request}

    data = field.to_representation(tag)

    assert "id" in data
    assert "url" in data
    assert "name" in data
    assert "type" in data
    assert data["id"] == tag.pk
    assert data["name"] == tag.name
    assert data["type"] == "tag"
    # Tags use name-based URL routing
    assert "/manager/api/" in data["url"]


@pytest.mark.django_db
def test_subject_field_representation_workflow_subject(api_rf, user_alice):
    """Test SubjectField serializes WorkflowSubject wrapper correctly."""
    surface = SurfaceFactory(created_by=user_alice)
    workflow_subject = AnalysisSubjectFactory(surface=surface)
    request = api_rf.get("/")

    field = SubjectField(read_only=True)
    field._context = {"request": request}

    data = field.to_representation(workflow_subject)

    assert "id" in data
    assert "url" in data
    assert "name" in data
    assert "type" in data
    assert data["id"] == surface.pk
    assert data["name"] == surface.name
    assert data["type"] == "surface"


# ============================================================================
# Test ManifestField
# ============================================================================


@pytest.mark.django_db
def test_manifest_field_representation_basic(api_rf, user_alice):
    """Test ManifestField serializes manifest with id and url."""
    manifest = ManifestFactory()
    request = api_rf.get("/")
    request.query_params = {}

    field = ManifestField(read_only=True)
    field._context = {"request": request}

    data = field.to_representation(manifest)

    assert "id" in data
    assert "url" in data
    assert data["id"] == manifest.pk
    assert f"/files/manifest/{manifest.pk}/" in data["url"]
    # File should not be included without link_file parameter
    assert "file" not in data


@pytest.mark.django_db
def test_manifest_field_representation_with_link_file(api_rf, user_alice):
    """Test ManifestField includes file URL when link_file query param is set."""
    manifest = ManifestFactory()
    request = api_rf.get("/")
    request.query_params = {"link_file": "true"}

    field = ManifestField(read_only=True)
    field._context = {"request": request}

    data = field.to_representation(manifest)

    assert "id" in data
    assert "url" in data
    assert "file" in data
    assert data["id"] == manifest.pk
    # File URL should be included
    assert data["file"] is not None


@pytest.mark.django_db
def test_manifest_field_representation_link_file_variations(api_rf, user_alice):
    """Test ManifestField recognizes different link_file parameter values."""
    manifest = ManifestFactory()

    # Test different truthy values
    for param_value in ["true", "1", "yes", "True", "YES"]:
        request = api_rf.get("/")
        request.query_params = {"link_file": param_value}
        field = ManifestField(read_only=True)
        field._context = {"request": request}
        data = field.to_representation(manifest)
        assert "file" in data, f"Failed for link_file={param_value}"

    # Test falsy values
    for param_value in ["false", "0", "no", "False", "NO"]:
        request = api_rf.get("/")
        request.query_params = {"link_file": param_value}
        field = ManifestField(read_only=True)
        field._context = {"request": request}
        data = field.to_representation(manifest)
        assert "file" not in data, f"Failed for link_file={param_value}"


# ============================================================================
# Test StringOrIntegerField
# ============================================================================


def test_string_or_integer_field_accepts_integer():
    """Test StringOrIntegerField accepts integer values."""
    field = StringOrIntegerField()

    result = field.to_internal_value(42)

    assert result == 42
    assert isinstance(result, int)


def test_string_or_integer_field_accepts_string():
    """Test StringOrIntegerField accepts string values."""
    field = StringOrIntegerField()

    result = field.to_internal_value("test_string")

    assert result == "test_string"
    assert isinstance(result, str)


def test_string_or_integer_field_rejects_other_types():
    """Test StringOrIntegerField rejects non-string, non-integer values."""
    field = StringOrIntegerField()

    with pytest.raises(ValidationError) as exc_info:
        field.to_internal_value(3.14)  # float

    assert "integer or a string" in str(exc_info.value).lower()

    with pytest.raises(ValidationError) as exc_info:
        field.to_internal_value([1, 2, 3])  # list

    assert "integer or a string" in str(exc_info.value).lower()


def test_string_or_integer_field_to_representation_integer():
    """Test StringOrIntegerField represents integer values correctly."""
    field = StringOrIntegerField()

    result = field.to_representation(42)

    assert result == 42


def test_string_or_integer_field_to_representation_string():
    """Test StringOrIntegerField represents string values correctly."""
    field = StringOrIntegerField()

    result = field.to_representation("test_string")

    assert result == "test_string"
