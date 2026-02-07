import pytest
from django.urls import reverse
from rest_framework import status

from topobank.analysis.models import Workflow, WorkflowResult
from topobank.manager.models import Tag
from topobank.testing.factories import (
    AnalysisFactory,
    SurfaceFactory,
    Topography1DFactory,
)

# ConfigurationView Tests


@pytest.mark.django_db
def test_configuration_view_retrieve(api_client, user_alice, handle_usage_statistics):
    """Test retrieving a configuration via v2 API"""
    topo = Topography1DFactory(created_by=user_alice)
    func = Workflow.objects.get(name="topobank.testing.test")

    # Create analysis which will have a configuration
    analysis = AnalysisFactory(
        subject_topography=topo,
        function=func,
        created_by=user_alice,
    )

    # Simulate having a configuration
    if analysis.configuration:
        api_client.force_login(user_alice)
        url = reverse("analysis:configuration-v2-detail", kwargs={"pk": analysis.configuration.pk})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "versions" in response.data
        assert isinstance(response.data["versions"], dict)


# WorkflowView Tests


@pytest.mark.django_db
def test_workflow_list_view(api_client, user_alice, handle_usage_statistics):
    """Test listing workflows via v2 API"""
    api_client.force_login(user_alice)

    url = reverse("analysis:workflow-v2-list")
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert "results" in response.data

    # Check that we have at least the test workflow
    workflows = response.data["results"]
    assert len(workflows) > 0
    assert response.data["count"] > 0

    # Check workflow structure
    workflow = workflows[0]
    assert "url" in workflow
    assert "name" in workflow
    assert "display_name" in workflow


@pytest.mark.django_db
def test_workflow_retrieve_view(
    api_client, user_alice, test_analysis_function, handle_usage_statistics
):
    """Test retrieving a specific workflow via v2 API"""
    api_client.force_login(user_alice)

    url = reverse("analysis:workflow-v2-detail", kwargs={"pk": test_analysis_function.pk})
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["name"] == test_analysis_function.name
    assert response.data["display_name"] == test_analysis_function.display_name
    assert "url" in response.data


@pytest.mark.django_db
def test_workflow_view_unauthenticated(api_client, handle_usage_statistics):
    """Test that unauthenticated users cannot access workflows"""
    url = reverse("analysis:workflow-v2-list")
    response = api_client.get(url)

    assert response.status_code == status.HTTP_403_FORBIDDEN


# ResultView Tests - List


@pytest.mark.django_db
def test_result_list_view(
    api_client, user_alice, one_line_scan, test_analysis_function, handle_usage_statistics
):
    """Test listing results via v2 API"""
    one_line_scan.created_by = user_alice
    one_line_scan.save()
    one_line_scan.grant_permission(user_alice, "view")

    # Create some analyses
    analysis1 = AnalysisFactory(
        subject_topography=one_line_scan,
        function=test_analysis_function,
        created_by=user_alice,
    )
    analysis1.permissions.grant_for_user(user_alice, "view")

    api_client.force_login(user_alice)
    url = reverse("analysis:result-v2-list")
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert "results" in response.data
    assert len(response.data["results"]) >= 1

    # Check result structure
    result = response.data["results"][0]
    assert "id" in result
    assert "url" in result
    assert "function" in result
    assert "subject" in result
    assert "task_state" in result
    assert "created_by" in result
    assert "permissions" in result

    # Ensure it is list view (not detail)
    assert "folder" not in result


@pytest.mark.django_db
def test_result_list_pagination(
    api_client, user_alice, one_line_scan, test_analysis_function, handle_usage_statistics
):
    """Test pagination of results list"""
    one_line_scan.created_by = user_alice
    one_line_scan.save()
    one_line_scan.grant_permission(user_alice, "view")

    # Create multiple analyses
    for _ in range(5):
        analysis = AnalysisFactory(
            subject_topography=one_line_scan,
            function=test_analysis_function,
            created_by=user_alice,
        )
        analysis.permissions.grant_for_user(user_alice, "view")

    url = reverse("analysis:result-v2-list")
    api_client.force_login(user_alice)
    response = api_client.get(url, {"limit": 2})

    assert response.status_code == status.HTTP_200_OK
    assert "results" in response.data
    assert "count" in response.data
    assert len(response.data["results"]) <= 2


# ResultView Tests - Create


@pytest.mark.django_db
def test_result_create_topography(
    api_client,
    user_alice,
    one_line_scan,
    test_analysis_function,
    handle_usage_statistics
):
    """Test creating a result for a topography via v2 API"""
    one_line_scan.created_by = user_alice
    one_line_scan.save()
    one_line_scan.grant_permission(user_alice, "view")

    url = reverse("analysis:result-v2-list")
    data = {
        "function": test_analysis_function.id,
        "subject": one_line_scan.id,
        "subject_type": "topography",
        "kwargs": {"a": 2, "b": "test"},
    }

    api_client.force_login(user_alice)
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert "id" in response.data
    assert response.data["function"]["name"] == test_analysis_function.name
    assert response.data["subject"]["id"] == one_line_scan.id
    assert response.data["subject"]["type"] == "topography"
    assert response.data["kwargs"] == {"a": 2, "b": "test"}
    assert response.data["created_by"]["id"] == user_alice.id
    assert response.data["task_state"] == WorkflowResult.NOTRUN

    # Verify it was created in the database
    analysis = WorkflowResult.objects.get(id=response.data["id"])
    assert analysis.function == test_analysis_function
    assert analysis.subject == one_line_scan
    assert analysis.kwargs == {"a": 2, "b": "test"}


@pytest.mark.django_db
def test_result_create_surface(
    api_client, user_alice, test_analysis_function, handle_usage_statistics
):
    """Test creating a result for a surface via v2 API"""
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
    assert response.data["subject"]["id"] == surface.id
    assert response.data["subject"]["type"] == "surface"
    assert response.data["function"]["name"] == test_analysis_function.name
    assert response.data["created_by"]["id"] == user_alice.id
    assert response.data["task_state"] == WorkflowResult.NOTRUN


@pytest.mark.django_db
def test_result_create_tag(api_client,
                           user_alice,
                           one_line_scan,
                           test_analysis_function,
                           handle_usage_statistics):
    """Test creating a result for a tag via v2 API"""
    api_client.force_login(user_alice)
    one_line_scan.created_by = user_alice
    one_line_scan.save()
    one_line_scan.surface.created_by = user_alice
    one_line_scan.surface.save()
    one_line_scan.surface.grant_permission(user_alice, "view")

    # Add tag to surface
    one_line_scan.surface.tags.add("test-tag")
    tag = Tag.objects.get(name="test-tag")

    url = reverse("analysis:result-v2-list")
    data = {
        "function": test_analysis_function.id,
        "subject": tag.id,
        "subject_type": "tag",
    }

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["subject"]["id"] == tag.id
    assert response.data["subject"]["type"] == "tag"
    assert response.data["function"]["name"] == test_analysis_function.name
    assert response.data["created_by"]["id"] == user_alice.id
    assert response.data["task_state"] == WorkflowResult.NOTRUN


@pytest.mark.django_db
def test_result_create_with_workflow_name(
    api_client,
    user_alice,
    one_line_scan,
    test_analysis_function,
    handle_usage_statistics
):
    """Test creating a result using workflow name instead of ID"""
    api_client.force_login(user_alice)
    one_line_scan.created_by = user_alice
    one_line_scan.save()
    one_line_scan.grant_permission(user_alice, "view")

    url = reverse("analysis:result-v2-list")
    data = {
        "function": test_analysis_function.name,
        "subject": one_line_scan.id,
        "subject_type": "topography",
    }

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["function"]["name"] == test_analysis_function.name
    assert response.data["created_by"]["id"] == user_alice.id
    assert response.data["task_state"] == WorkflowResult.NOTRUN


@pytest.mark.django_db
def test_result_create_invalid_subject_type(
    api_client,
    user_alice,
    one_line_scan,
    test_analysis_function,
    handle_usage_statistics
):
    """Test creating a result with invalid subject type"""
    api_client.force_login(user_alice)

    url = reverse("analysis:result-v2-list")
    data = {
        "function": test_analysis_function.id,
        "subject": one_line_scan.id,
        "subject_type": "invalid_type",
    }

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_result_create_nonexistent_subject(
    api_client, user_alice, test_analysis_function, handle_usage_statistics
):
    """Test creating a result with non-existent subject"""
    api_client.force_login(user_alice)

    url = reverse("analysis:result-v2-list")
    data = {
        "function": test_analysis_function.id,
        "subject": 99999,
        "subject_type": "topography",
    }

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_result_create_no_permission(
    api_client,
    user_alice,
    user_bob,
    one_line_scan,
    test_analysis_function,
    handle_usage_statistics
):
    """Test creating a result for a subject user doesn't have permission to"""
    one_line_scan.created_by = user_alice
    one_line_scan.save()

    # Login as Bob who has no permissions
    api_client.force_login(user_bob)

    url = reverse("analysis:result-v2-list")
    data = {
        "function": test_analysis_function.id,
        "subject": one_line_scan.id,
        "subject_type": "topography",
    }

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST


# ResultView Tests - Retrieve


@pytest.mark.django_db
def test_result_retrieve_view(
    api_client,
    user_alice,
    one_line_scan,
    test_analysis_function,
    handle_usage_statistics
):
    """Test retrieving a specific result via v2 API"""
    one_line_scan.created_by = user_alice
    one_line_scan.save()

    api_client.force_login(user_alice)

    analysis = AnalysisFactory(
        subject_topography=one_line_scan,
        function=test_analysis_function,
        created_by=user_alice,
    )
    analysis.permissions.grant_for_user(user_alice, "view")

    url = reverse("analysis:result-v2-detail", kwargs={"pk": analysis.pk})
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["id"] == analysis.pk
    assert "dependencies" in response.data
    assert "folder" in response.data
    assert "configuration" in response.data
    assert "task_state" in response.data
    assert "task_messages" in response.data
    assert "dois" in response.data
    assert "metadata" in response.data
    assert response.data['created_by']['id'] == user_alice.id


@pytest.mark.django_db
def test_result_retrieve_no_permission(
    api_client,
    user_alice,
    user_bob,
    one_line_scan,
    test_analysis_function,
    handle_usage_statistics
):
    """Test retrieving a result without permission"""
    one_line_scan.created_by = user_alice
    one_line_scan.save()

    # Login as Bob who has no permissions
    api_client.force_login(user_bob)

    analysis = AnalysisFactory(
        subject_topography=one_line_scan,
        function=test_analysis_function,
        created_by=user_alice,
    )

    url = reverse("analysis:result-v2-detail", kwargs={"pk": analysis.pk})
    response = api_client.get(url)

    assert response.status_code == status.HTTP_404_NOT_FOUND


# ResultView Tests - Update


@pytest.mark.django_db
def test_result_update_name(
    api_client,
    user_alice,
    one_line_scan,
    test_analysis_function,
    handle_usage_statistics
):
    """Test updating result name via v2 API"""
    one_line_scan.created_by = user_alice
    one_line_scan.save()

    analysis = AnalysisFactory(
        subject_topography=one_line_scan,
        function=test_analysis_function,
        created_by=user_alice,
    )
    analysis.permissions.grant_for_user(user_alice, "edit")

    api_client.force_login(user_alice)
    url = reverse("analysis:result-v2-detail", kwargs={"pk": analysis.pk})
    data = {
        "name": "Updated Analysis Name",
        "description": "Updated description",
    }

    response = api_client.patch(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["name"] == "Updated Analysis Name"
    assert response.data["description"] == "Updated description"
    assert response.data["id"] == analysis.pk
    # Verify updated_by field
    assert response.data["updated_by"]["id"] == user_alice.id
    # Verify subject was set to None when analysis is named
    assert response.data['subject'] is None

    # Verify in database
    analysis.refresh_from_db()
    assert analysis.name == "Updated Analysis Name"
    assert analysis.description == "Updated description"


@pytest.mark.django_db
def test_result_update_no_permission(
    api_client,
    user_alice,
    user_bob,
    one_line_scan,
    test_analysis_function,
    handle_usage_statistics
):
    """Test updating a result without permission"""
    one_line_scan.created_by = user_alice
    one_line_scan.save()

    analysis = AnalysisFactory(
        subject_topography=one_line_scan,
        function=test_analysis_function,
        created_by=user_alice,
    )

    # Login as Bob who has no permissions
    api_client.force_login(user_bob)
    url = reverse("analysis:result-v2-detail", kwargs={"pk": analysis.pk})
    data = {"name": "Hacked Name"}

    response = api_client.patch(url, data, format="json")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_result_update_insufficient_permission(
    api_client,
    user_alice,
    user_bob,
    one_line_scan,
    test_analysis_function,
    handle_usage_statistics
):
    """Test updating a result with insufficient permission"""
    one_line_scan.created_by = user_alice
    one_line_scan.save()

    analysis = AnalysisFactory(
        subject_topography=one_line_scan,
        function=test_analysis_function,
        created_by=user_alice,
    )

    analysis.permissions.grant_for_user(user_bob, "view")

    # Login as Bob who has view permissions
    api_client.force_login(user_bob)
    url = reverse("analysis:result-v2-detail", kwargs={"pk": analysis.pk})

    response = api_client.get(url)
    # Ensure Bob can view
    assert response.status_code == status.HTTP_200_OK

    data = {"name": "Hacked Name"}
    response = api_client.patch(url, data, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN


# ResultView Tests - Delete


@pytest.mark.django_db
def test_result_delete(
    api_client, user_alice, one_line_scan, test_analysis_function, handle_usage_statistics
):
    """Test deleting a result via v2 API"""
    one_line_scan.created_by = user_alice
    one_line_scan.save()

    analysis = AnalysisFactory(
        subject_topography=one_line_scan,
        function=test_analysis_function,
        created_by=user_alice,
    )
    analysis.permissions.grant_for_user(user_alice, "full")

    api_client.force_login(user_alice)
    url = reverse("analysis:result-v2-detail", kwargs={"pk": analysis.pk})
    response = api_client.delete(url)

    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Verify it was deleted
    assert not WorkflowResult.objects.filter(pk=analysis.id).exists()


@pytest.mark.django_db
def test_result_delete_no_permission(
    api_client,
    user_alice,
    user_bob,
    one_line_scan,
    test_analysis_function,
    handle_usage_statistics
):
    """Test deleting a result without permission"""
    one_line_scan.created_by = user_alice
    one_line_scan.save()

    analysis = AnalysisFactory(
        subject_topography=one_line_scan,
        function=test_analysis_function,
        created_by=user_alice,
    )

    # Login as Bob who has no permissions
    api_client.force_login(user_bob)
    url = reverse("analysis:result-v2-detail", kwargs={"pk": analysis.pk})
    response = api_client.delete(url)

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_result_delete_insufficient_permission(
    api_client,
    user_alice,
    user_bob,
    one_line_scan,
    test_analysis_function,
    handle_usage_statistics
):
    """Test deleting a result with insufficient permission"""
    one_line_scan.created_by = user_alice
    one_line_scan.save()

    analysis = AnalysisFactory(
        subject_topography=one_line_scan,
        function=test_analysis_function,
        created_by=user_alice,
    )
    analysis.permissions.grant_for_user(user_bob, "view")

    # Login as Bob who has view permissions
    api_client.force_login(user_bob)
    url = reverse("analysis:result-v2-detail", kwargs={"pk": analysis.pk})
    response = api_client.delete(url)

    assert response.status_code == status.HTTP_403_FORBIDDEN

    # Try again with edit permissions
    analysis.permissions.grant_for_user(user_bob, "edit")
    response = api_client.delete(url)

    assert response.status_code == status.HTTP_403_FORBIDDEN


# ResultView Tests - Run Action


@pytest.mark.django_db
def test_result_run_action(
    api_client,
    user_alice,
    one_line_scan,
    test_analysis_function,
    django_capture_on_commit_callbacks,
    handle_usage_statistics
):
    """Test running a result via v2 API"""
    one_line_scan.created_by = user_alice
    one_line_scan.task_state = WorkflowResult.SUCCESS  # Ensure topography is ready
    one_line_scan.save()
    one_line_scan.grant_permission(user_alice, "view")

    analysis = AnalysisFactory(
        subject_topography=one_line_scan,
        function=test_analysis_function,
        created_by=user_alice,
        task_state=WorkflowResult.NOTRUN,
    )
    analysis.permissions.grant_for_user(user_alice, "edit")

    url = reverse("analysis:result-v2-run", kwargs={"pk": analysis.pk})

    api_client.force_login(user_alice)
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.post(url)

    assert response.status_code == status.HTTP_202_ACCEPTED
    assert response.data['updated_by']['id'] == user_alice.id
    # Verify callback was registered (task was submitted)
    assert len(callbacks) > 0


@pytest.mark.django_db
def test_result_run_action_already_running(
    api_client,
    user_alice,
    one_line_scan,
    test_analysis_function,
    handle_usage_statistics
):
    """Test running a result that is already running"""
    one_line_scan.created_by = user_alice
    one_line_scan.task_state = WorkflowResult.SUCCESS  # Ensure topography is ready
    one_line_scan.save()
    one_line_scan.grant_permission(user_alice, "view")

    analysis = AnalysisFactory(
        subject_topography=one_line_scan,
        function=test_analysis_function,
        created_by=user_alice,
        task_state=WorkflowResult.SUCCESS,
    )
    analysis.permissions.grant_for_user(user_alice, "edit")

    url = reverse("analysis:result-v2-run", kwargs={"pk": analysis.pk})
    api_client.force_login(user_alice)
    response = api_client.post(url)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "already running or completed" in response.data["message"]


@pytest.mark.django_db
def test_result_run_action_with_force(
    api_client,
    user_alice,
    one_line_scan,
    test_analysis_function,
    django_capture_on_commit_callbacks,
    handle_usage_statistics
):
    """Test force re-running a completed result"""
    one_line_scan.created_by = user_alice
    one_line_scan.task_state = WorkflowResult.SUCCESS  # Ensure topography is ready
    one_line_scan.save()
    one_line_scan.grant_permission(user_alice, "view")

    analysis = AnalysisFactory(
        subject_topography=one_line_scan,
        function=test_analysis_function,
        created_by=user_alice,
        updated_by=user_alice,
        task_state=WorkflowResult.SUCCESS,
    )
    analysis.permissions.grant_for_user(user_alice, "edit")

    url = reverse("analysis:result-v2-run", kwargs={"pk": analysis.pk})

    api_client.force_login(user_alice)
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.post(f"{url}?force=true")

    assert response.status_code == status.HTTP_202_ACCEPTED
    # Verify callback was registered (task was submitted)
    assert len(callbacks) > 0


@pytest.mark.django_db
def test_result_run_action_named_analysis(
    api_client,
    user_alice,
    one_line_scan,
    test_analysis_function,
    handle_usage_statistics
):
    """Test running a named analysis (should fail)"""
    one_line_scan.created_by = user_alice
    one_line_scan.save()
    one_line_scan.grant_permission(user_alice, "view")

    analysis = AnalysisFactory(
        subject_topography=one_line_scan,
        function=test_analysis_function,
        created_by=user_alice,
        updated_by=user_alice,
        name="My Named Analysis",
        task_state=WorkflowResult.NOTRUN,
    )
    analysis.permissions.grant_for_user(user_alice, "edit")

    url = reverse("analysis:result-v2-run", kwargs={"pk": analysis.pk})
    api_client.force_login(user_alice)
    response = api_client.post(url)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "Cannot renew named analysis" in response.data["message"]


@pytest.mark.django_db
def test_result_run_action_subject_not_ready(
    api_client,
    user_alice,
    test_analysis_function,
    handle_usage_statistics
):
    """Test running an analysis when subject is not ready"""

    topo = Topography1DFactory(
        created_by=user_alice,
        task_state=WorkflowResult.PENDING  # Not in SUCCESS state
    )
    topo.grant_permission(user_alice, "view")

    analysis = AnalysisFactory(
        subject_topography=topo,
        function=test_analysis_function,
        created_by=user_alice,
        task_state=WorkflowResult.NOTRUN,
    )
    analysis.permissions.grant_for_user(user_alice, "edit")

    api_client.force_login(user_alice)
    url = reverse("analysis:result-v2-run", kwargs={"pk": analysis.pk})
    response = api_client.post(url)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "not ready" in response.data["message"]


# ResultView Tests - Dependencies Action


@pytest.mark.django_db
def test_result_dependencies_action(
    api_client,
    user_alice,
    one_line_scan,
    test_analysis_function,
    handle_usage_statistics
):
    """Test retrieving dependencies for a result"""
    one_line_scan.created_by = user_alice
    one_line_scan.save()
    one_line_scan.grant_permission(user_alice, "view")

    # Create main analysis
    analysis = AnalysisFactory(
        subject_topography=one_line_scan,
        function=test_analysis_function,
        created_by=user_alice,
    )
    analysis.permissions.grant_for_user(user_alice, "view")

    # Create dependency
    dep_analysis = AnalysisFactory(
        subject_topography=one_line_scan,
        function=test_analysis_function,
        created_by=user_alice,
    )
    dep_analysis.permissions.grant_for_user(user_alice, "view")

    # Set dependencies
    analysis.dependencies = {str(one_line_scan.id): dep_analysis.id}
    analysis.save()

    url = reverse("analysis:result-v2-dependency", kwargs={"pk": analysis.pk})
    api_client.force_login(user_alice)
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert "results" in response.data
    results = response.data["results"]
    assert len(results) == 1
    assert results[0]["id"] == dep_analysis.id
    assert "url" in results[0]
    assert "task_state" in results[0]


@pytest.mark.django_db
def test_result_dependencies_empty(
    api_client,
    user_alice,
    one_line_scan,
    test_analysis_function,
    handle_usage_statistics
):
    """Test retrieving dependencies when there are none"""
    one_line_scan.created_by = user_alice
    one_line_scan.save()
    one_line_scan.grant_permission(user_alice, "view")

    analysis = AnalysisFactory(
        subject_topography=one_line_scan,
        function=test_analysis_function,
        created_by=user_alice,
    )
    analysis.permissions.grant_for_user(user_alice, "view")
    analysis.dependencies = {}
    analysis.save()

    url = reverse("analysis:result-v2-dependency", kwargs={"pk": analysis.pk})
    api_client.force_login(user_alice)
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert "results" in response.data
    assert len(response.data["results"]) == 0


@pytest.mark.django_db
def test_result_dependencies_pagination(
    api_client,
    user_alice,
    one_line_scan,
    test_analysis_function,
    handle_usage_statistics
):
    """Test pagination of dependencies"""
    one_line_scan.created_by = user_alice
    one_line_scan.save()
    one_line_scan.grant_permission(user_alice, "view")

    analysis = AnalysisFactory(
        subject_topography=one_line_scan,
        function=test_analysis_function,
        created_by=user_alice,
    )
    analysis.permissions.grant_for_user(user_alice, "view")

    # Create multiple dependencies
    dependencies = {}
    for i in range(5):
        dep_analysis = AnalysisFactory(
            subject_topography=one_line_scan,
            function=test_analysis_function,
            created_by=user_alice,
        )
        dep_analysis.permissions.grant_for_user(user_alice, "view")
        dependencies[f"subject_{i}"] = dep_analysis.id

    analysis.dependencies = dependencies
    analysis.save()

    url = reverse("analysis:result-v2-dependency", kwargs={"pk": analysis.pk})
    api_client.force_login(user_alice)
    response = api_client.get(url, {"limit": 2})

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) <= 2
    assert "count" in response.data
    assert response.data["count"] == 5
    assert "next" in response.data
    assert response.data["next"] is not None


@pytest.mark.django_db
def test_result_dependencies_no_permission(
    api_client,
    user_alice,
    user_bob,
    one_line_scan,
    test_analysis_function,
    handle_usage_statistics
):
    """Test retrieving dependencies without permission"""
    one_line_scan.created_by = user_alice
    one_line_scan.save()

    analysis = AnalysisFactory(
        subject_topography=one_line_scan,
        function=test_analysis_function,
        created_by=user_alice,
    )

    url = reverse("analysis:result-v2-dependency", kwargs={"pk": analysis.pk})
    api_client.force_login(user_bob)
    response = api_client.get(url)

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_result_view_unauthenticated(api_client, handle_usage_statistics):
    """Test that unauthenticated users cannot access results"""
    url = reverse("analysis:result-v2-list")
    response = api_client.get(url)

    assert response.status_code == status.HTTP_403_FORBIDDEN
