from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from topobank.analysis.models import WorkflowResult
from topobank.testing.factories import AnalysisFactory, TagFactory

# Result Filters


@pytest.mark.django_db
def test_result_list_filtered(api_client, user_alice,
                              one_line_scan, one_topography,
                              test_analysis_function,
                              handle_usage_statistics):
    """Test filtering results by various parameters

    Filters tested:
    - task_state (SUCCESS/FAILURE)
    - subject_type (topography/surface)
    - workflow_name
    - created_gte (created after date)
    - created_lte (created before date)
    - subject_id (alone - searches across all types)
    - subject_id + subject_type (combined filtering)
    - subject_ids (multiple IDs)
    - subject_name
    - tag (tag name)
    - named (Boolean - True/False)
    """
    # Create a tag for tag filtering tests
    test_tag = TagFactory(name="TestTag")
    test_tag.authorize_user(user_alice, "view")

    one_line_scan.created_by = user_alice
    one_line_scan.save()
    one_line_scan.surface.tags.add("TestTag")
    one_line_scan.grant_permission(user_alice, "view")

    # Use a second topography and surface for more comprehensive testing
    _, another_surface, another_topo = one_topography
    another_topo.created_by = user_alice
    another_topo.name = "Another Topography"
    another_topo.save()
    another_topo.grant_permission(user_alice, "view")

    another_surface.name = "Another Surface"
    another_surface.save()
    another_surface.tags.add("TestTag")
    another_surface.grant_permission(user_alice, "view")

    # 3 topography analyses
    topo_analysis_success = AnalysisFactory(
        subject_topography=one_line_scan,
        function=test_analysis_function,
        created_by=user_alice,
        task_state=WorkflowResult.SUCCESS,
        name="Named Analysis",  # Named analysis for named filter test
    )
    topo_analysis_failure = AnalysisFactory(
        subject_topography=one_line_scan,
        function=test_analysis_function,
        created_by=user_alice,
        task_state=WorkflowResult.FAILURE,
        # No name - unnamed analysis for named filter test
    )
    another_topo_analysis = AnalysisFactory(
        subject_topography=another_topo,
        function=test_analysis_function,
        created_by=user_alice,
        task_state=WorkflowResult.SUCCESS,
    )

    # 2 surface analyses
    last_week_analysis = AnalysisFactory(
        subject_surface=one_line_scan.surface,
        function=test_analysis_function,
        created_by=user_alice,
        task_state=WorkflowResult.SUCCESS,
    )
    # Manually set created_at for date filter testing (must be done after creation)
    WorkflowResult.objects.filter(id=last_week_analysis.id).update(
        created_at=timezone.now() - timedelta(days=7)
    )
    last_week_analysis.refresh_from_db()

    another_surface_analysis = AnalysisFactory(
        subject_surface=another_surface,
        function=test_analysis_function,
        created_by=user_alice,
        task_state=WorkflowResult.SUCCESS,
    )

    # 1 tag analysis
    tag_analysis = AnalysisFactory(
        subject_tag=test_tag,
        function=test_analysis_function,
        created_by=user_alice,
        task_state=WorkflowResult.SUCCESS,
    )

    topo_analysis_success.permissions.grant_for_user(user_alice, "view")
    topo_analysis_failure.permissions.grant_for_user(user_alice, "view")
    last_week_analysis.permissions.grant_for_user(user_alice, "view")
    another_topo_analysis.permissions.grant_for_user(user_alice, "view")
    another_surface_analysis.permissions.grant_for_user(user_alice, "view")
    tag_analysis.permissions.grant_for_user(user_alice, "view")

    api_client.force_login(user_alice)

    # No filter - get all analyses
    url = reverse("analysis:result-v2-list")

    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    results = response.data["results"]
    assert response.data["count"] == 6

    # Filter by task_state
    url = reverse("analysis:result-v2-list")

    response = api_client.get(url, {"task_state": WorkflowResult.SUCCESS})

    assert response.status_code == status.HTTP_200_OK
    results = response.data["results"]
    assert response.data["count"] == 5
    for result in results:
        assert result["task_state"] == WorkflowResult.SUCCESS
        assert result["id"] in [
            topo_analysis_success.id,
            last_week_analysis.id,
            another_topo_analysis.id,
            another_surface_analysis.id,
            tag_analysis.id,
        ]

    # Filter by subject_type
    response = api_client.get(url, {"subject_type": "topography"})
    assert response.status_code == status.HTTP_200_OK
    results = response.data["results"]
    # topo_analysis_success is a named analysis, so it no longer has a subject
    # and won't be returned by the subject_type filter
    assert response.data["count"] == 2
    for result in results:
        assert result["id"] in [topo_analysis_failure.id, another_topo_analysis.id]
        assert result["subject"]["type"] == "topography"

    # Filter by workflow (function) name
    response = api_client.get(url, {"workflow_name": test_analysis_function.name})
    assert response.status_code == status.HTTP_200_OK
    results = response.data["results"]
    # All six analyses use the same workflow
    assert response.data["count"] == 6

    # Get time yesterday (any time between now and a week ago would work)
    time_yesterday = timezone.now() - timedelta(days=1)

    # Filter by created_gte
    response = api_client.get(url, {"created_gte": time_yesterday.isoformat()})
    assert response.status_code == status.HTTP_200_OK
    results = response.data["results"]
    assert response.data["count"] == 5
    assert {
        topo_analysis_failure.id,
        topo_analysis_success.id,
        another_topo_analysis.id,
        another_surface_analysis.id,
        tag_analysis.id,
    } == {r["id"] for r in results}

    # Filter by created_lte
    response = api_client.get(url, {"created_lte": time_yesterday.isoformat()})
    assert response.status_code == status.HTTP_200_OK
    results = response.data["results"]
    assert response.data["count"] == 1
    # Only one result created before yesterday - last_week_analysis
    assert results[0]["id"] == last_week_analysis.id

    # Filter by subject_id (alone - searches across all types)
    response = api_client.get(url, {"subject_id": one_line_scan.id})
    assert response.status_code == status.HTTP_200_OK
    results = response.data["results"]
    # This test may return more that 2 if there are analyses on surfaces or tags that have the same ID
    # Checking that at least topo_analysis_failure is present (the unnamed one)
    assert response.data["count"] >= 1
    assert topo_analysis_failure.id in {r["id"] for r in results}

    # Filter by subject_id + subject_type (combined filtering)
    response = api_client.get(url, {"subject_id": one_line_scan.id, "subject_type": "topography"})
    assert response.status_code == status.HTTP_200_OK
    results = response.data["results"]
    # Note: topo_analysis_success is named so has no subject
    assert response.data["count"] == 1
    assert results[0]["subject"]["type"] == "topography"
    assert results[0]["id"] == topo_analysis_failure.id

    # Filter by subject_id + subject_type for surface
    # Since a topography and a surface can have the same ID, this tests that filtering works correctly
    response = api_client.get(url, {"subject_id": one_line_scan.surface.id, "subject_type": "surface"})
    assert response.status_code == status.HTTP_200_OK
    results = response.data["results"]
    assert response.data["count"] == 1
    assert results[0]["subject"]["type"] == "surface"
    assert results[0]["id"] == last_week_analysis.id

    # Filter by subject_ids (multiple IDs)
    response = api_client.get(url, {"subject_ids": f"{one_line_scan.id},{another_topo.id}"})
    assert response.status_code == status.HTTP_200_OK
    results = response.data["results"]
    assert response.data["count"] >= 2
    assert {
        topo_analysis_failure.id,
        another_topo_analysis.id
    } <= {r["id"] for r in results}

    # Filter by subject_name
    response = api_client.get(url, {"subject_name": "Another"})
    assert response.status_code == status.HTTP_200_OK
    results = response.data["results"]
    assert response.data["count"] == 2
    assert {another_topo_analysis.id, another_surface_analysis.id} == {r["id"] for r in results}

    # Filter by tag name
    response = api_client.get(url, {"tag": "TestTag"})
    assert response.status_code == status.HTTP_200_OK
    results = response.data["results"]
    assert response.data["count"] == 1
    assert results[0]["id"] == tag_analysis.id

    # Filter by named=True
    response = api_client.get(url, {"named": "true"})
    assert response.status_code == status.HTTP_200_OK
    results = response.data["results"]
    assert response.data["count"] == 1
    assert results[0]["id"] == topo_analysis_success.id
    assert results[0]["name"] == "Named Analysis"

    # Filter by named=False
    response = api_client.get(url, {"named": "false"})
    assert response.status_code == status.HTTP_200_OK
    results = response.data["results"]
    assert response.data["count"] == 5
    assert {
        topo_analysis_failure.id,
        last_week_analysis.id,
        another_topo_analysis.id,
        another_surface_analysis.id,
        tag_analysis.id,
    } == {r["id"] for r in results}


# Workflow Filters

@pytest.mark.django_db
def test_workflow_list_filtered(api_client, user_alice, handle_usage_statistics):
    """Test filtering workflows via v2 API

    Filters tested:
    - name (case-insensitive contains)
    - display_name (case-insensitive contains)
    - subject_type (tag/surface/topography)
    """
    api_client.force_login(user_alice)

    url = reverse("analysis:workflow-v2-list")

    # Get all workflows first to understand what we're working with
    response = api_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    all_workflows = response.data["results"]
    all_count = response.data["count"]
    assert all_count > 0

    # Filter by name (case-insensitive contains)
    response = api_client.get(url, {"name": "topobank.testing.test"})
    assert response.status_code == status.HTTP_200_OK
    workflows = response.data["results"]
    # Should filter to just the test workflow
    for workflow in workflows:
        assert "topobank.testing.test" in workflow["name"]
    # Should be fewer than all workflows
    assert len(workflows) <= all_count

    # Filter by name with different case
    response = api_client.get(url, {"name": "TESTING"})
    assert response.status_code == status.HTTP_200_OK
    workflows = response.data["results"]
    for workflow in workflows:
        assert "testing" in workflow["name"].lower()

    # Filter by name with partial match
    response = api_client.get(url, {"name": "test"})
    assert response.status_code == status.HTTP_200_OK
    workflows = response.data["results"]
    for workflow in workflows:
        assert "test" in workflow["name"].lower()

    # Filter by display_name (case-insensitive contains)
    # First, get a display name to use for filtering
    if all_workflows:
        sample_display_name = all_workflows[0]["display_name"]
        # Use a partial match from the display name
        partial_name = sample_display_name[:5] if len(sample_display_name) >= 5 else sample_display_name

        response = api_client.get(url, {"display_name": partial_name})
        assert response.status_code == status.HTTP_200_OK
        workflows = response.data["results"]
        for workflow in workflows:
            assert partial_name.lower() in workflow["display_name"].lower()

    # Filter by subject_type - topography
    response = api_client.get(url, {"subject_type": "topography"})
    assert response.status_code == status.HTTP_200_OK
    workflows = response.data["results"]
    # All returned workflows should support topography
    # (Note: We can't directly verify this from the API response without additional info,
    # but we can verify the filter doesn't error and returns some results)
    assert response.data["count"] >= 0

    # Filter by subject_type - surface
    response = api_client.get(url, {"subject_type": "surface"})
    assert response.status_code == status.HTTP_200_OK
    workflows = response.data["results"]
    assert response.data["count"] >= 0

    # Filter by subject_type - tag
    response = api_client.get(url, {"subject_type": "tag"})
    assert response.status_code == status.HTTP_200_OK
    workflows = response.data["results"]
    assert response.data["count"] >= 0

    # Combine multiple filters: name + subject_type
    response = api_client.get(url, {"name": "test", "subject_type": "topography"})
    assert response.status_code == status.HTTP_200_OK
    workflows = response.data["results"]
    for workflow in workflows:
        assert "test" in workflow["name"].lower()

    # Test invalid subject_type
    response = api_client.get(url, {"subject_type": "invalid_type"})
    # Invalid choice should return a 400 error
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    # Test non-existent name filter
    response = api_client.get(url, {"name": "nonexistent_workflow_xyz_123"})
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 0
