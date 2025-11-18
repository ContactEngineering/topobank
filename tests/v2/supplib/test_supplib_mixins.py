import pytest
from django.urls import reverse
from rest_framework import serializers, status

from topobank.analysis.models import WorkflowResult
from topobank.supplib.mixins import StrictFieldMixin
from topobank.testing.factories import SurfaceFactory

# ============================================================================
# Test StrictFieldMixin
# ============================================================================


class StrictTestSerializer(StrictFieldMixin, serializers.Serializer):
    """Test serializer with StrictFieldMixin for validation testing."""

    name = serializers.CharField(max_length=100)
    description = serializers.CharField(max_length=500, required=False)
    read_only_field = serializers.CharField(read_only=True)

    class Meta:
        read_only_fields = ["read_only_field"]


@pytest.mark.django_db
def test_strict_field_mixin_valid_data():
    """Test StrictFieldMixin accepts valid data with defined fields."""
    data = {"name": "Test Name", "description": "Test Description"}
    serializer = StrictTestSerializer(data=data)

    assert serializer.is_valid()
    assert serializer.validated_data["name"] == "Test Name"
    assert serializer.validated_data["description"] == "Test Description"


@pytest.mark.django_db
def test_strict_field_mixin_rejects_unknown_fields():
    """Test StrictFieldMixin rejects data with unknown fields."""
    data = {"name": "Test Name", "unknown_field": "Some Value"}
    serializer = StrictTestSerializer(data=data)

    assert not serializer.is_valid()
    assert "unknown_field" in serializer.errors
    assert "does not exist" in str(serializer.errors["unknown_field"])


@pytest.mark.django_db
def test_strict_field_mixin_rejects_read_only_fields():
    """Test StrictFieldMixin rejects data with read-only fields.

    Note: Read-only fields are rejected with 'does not exist' error because they're
    not in the writable fields list checked by to_internal_value().
    """
    data = {"name": "Test Name", "read_only_field": "Should Fail"}
    serializer = StrictTestSerializer(data=data)

    assert not serializer.is_valid()
    assert "read_only_field" in serializer.errors
    # Read-only fields get rejected as "does not exist" in to_internal_value
    assert "does not exist" in str(serializer.errors["read_only_field"]).lower()


@pytest.mark.django_db
def test_strict_field_mixin_multiple_errors():
    """Test StrictFieldMixin reports multiple validation errors."""
    data = {
        "name": "Test Name",
        "read_only_field": "Should Fail",
        "unknown_field": "Also Fails",
    }
    serializer = StrictTestSerializer(data=data)

    assert not serializer.is_valid()
    assert "read_only_field" in serializer.errors
    assert "unknown_field" in serializer.errors


# ============================================================================
# Test UserUpdateMixin
# ============================================================================


@pytest.mark.django_db
def test_user_update_mixin(api_client, user_alice, user_bob, test_analysis_function, handle_usage_statistics):
    """Test create and update fields auto apply via v2 API"""
    surface = SurfaceFactory(created_by=user_alice)
    surface.grant_permission(user_alice, "view")

    api_client.force_login(user_alice)
    url = reverse("analysis:result-v2-list")
    data = {
        "function": test_analysis_function.id,
        "subject": surface.id,
        "subject_type": "surface",
    }

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_201_CREATED

    # Check that the created_by field is set correctly
    assert response.data["created_by"]["id"] == user_alice.id
    assert response.data["updated_by"]["id"] == user_alice.id

    created_workflow_result = WorkflowResult.objects.get(id=response.data["id"])
    created_workflow_result.grant_permission(user_bob, "edit")

    api_client.force_login(user_bob)
    update_url = reverse("analysis:result-v2-detail", kwargs={"pk": created_workflow_result.id})
    update_data = {
        "name": "Updated Analysis Name"
    }

    response = api_client.patch(update_url, update_data, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["name"] == "Updated Analysis Name"
    assert response.data["updated_by"]["id"] == user_bob.id
    assert response.data["created_by"]["id"] == user_alice.id
