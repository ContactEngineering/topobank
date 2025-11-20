import pytest
from rest_framework.request import Request

from topobank.manager.models import Surface
from topobank.supplib.mixins import StrictFieldMixin
from topobank.supplib.serializers import (
    DynamicFieldsModelSerializer,
    PermissionsField,
    UserField,
)
from topobank.testing.factories import SurfaceFactory

# ============================================================================
# Integration Tests - Combining Mixins/Serializers
# ============================================================================


class IntegrationTestSerializer(StrictFieldMixin, DynamicFieldsModelSerializer):
    """Test serializer combining StrictFieldMixin and DynamicFieldsModelSerializer."""

    created_by = UserField(read_only=True)
    permissions = PermissionsField(read_only=True)

    class Meta:
        model = Surface
        fields = ["id", "name", "description", "created_by", "permissions"]
        read_only_fields = ["id"]


@pytest.mark.django_db
def test_integration_combined_mixins(api_rf, user_alice):
    """Test combining StrictFieldMixin with DynamicFieldsModelSerializer."""

    surface = SurfaceFactory(created_by=user_alice)
    wsgi_request = api_rf.get("/?fields=id,name,created_by")
    request = Request(wsgi_request)
    request.user = user_alice

    serializer = IntegrationTestSerializer(surface, context={"request": request})
    data = serializer.data

    # Only specified fields should be present
    assert "id" in data
    assert "name" in data
    assert "created_by" in data
    assert "description" not in data
    assert "permissions" not in data

    # UserField should have correct structure
    assert "name" in data["created_by"]
    assert data["created_by"]["name"] == user_alice.name


@pytest.mark.django_db
def test_integration_strict_validation_with_write(api_rf, user_alice):
    """Test StrictFieldMixin validation during write operations."""

    wsgi_request = api_rf.post("/")
    request = Request(wsgi_request)
    request.user = user_alice

    # Valid data should work
    valid_data = {"name": "Test Surface", "description": "Test Description"}
    serializer = IntegrationTestSerializer(data=valid_data, context={"request": request})
    assert serializer.is_valid()

    # Data with read-only field should fail
    invalid_data = {"id": 999, "name": "Test Surface"}
    serializer = IntegrationTestSerializer(data=invalid_data, context={"request": request})
    assert not serializer.is_valid()
    assert "id" in serializer.errors

    # Data with unknown field should fail
    invalid_data = {"name": "Test Surface", "unknown": "value"}
    serializer = IntegrationTestSerializer(data=invalid_data, context={"request": request})
    assert not serializer.is_valid()
    assert "unknown" in serializer.errors
