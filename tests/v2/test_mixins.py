import pytest
from django.urls import reverse
from rest_framework import status

from topobank.analysis.models import WorkflowResult
from topobank.testing.factories import SurfaceFactory


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
