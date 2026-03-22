"""Tests for PlanRecord model and WorkflowResult plan fields."""

import pytest

from topobank.analysis.models import PlanRecord, Workflow, WorkflowResult
from topobank.authorization import get_permission_model
from topobank.testing.factories import (
    Topography1DFactory,
    TopographyAnalysisFactory,
    UserFactory,
)


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def permissions(db):
    return get_permission_model().objects.create()


@pytest.fixture
def sample_plan_json():
    """Sample WorkflowPlan serialized as JSON."""
    return {
        "root_key": "data-lake/results/test.workflow/abc123",
        "nodes": {
            "data-lake/results/test.workflow/abc123": {
                "key": "data-lake/results/test.workflow/abc123",
                "function": "topobank.testing.test",
                "subject_key": "topography:1",
                "kwargs": {"param": "value"},
                "storage_prefix": "data-lake/results/test.workflow/abc123",
                "depends_on": [],
                "depended_on_by": [],
                "output_files": ["result.json"],
                "cached": False,
                "analysis_id": None,
            }
        },
    }


@pytest.mark.django_db
class TestPlanRecordModel:
    """Tests for PlanRecord model."""

    def test_create_plan_record(self, user, permissions, sample_plan_json):
        """Test creating a PlanRecord with valid data."""
        plan = PlanRecord.objects.create(
            plan_json=sample_plan_json,
            root_kwargs={"param": "value"},
            created_by=user,
            permissions=permissions,
        )

        assert plan.id is not None
        assert plan.state == PlanRecord.PENDING
        assert plan.plan_json == sample_plan_json
        assert plan.created_by == user
        assert plan.started_at is None
        assert plan.completed_at is None
        assert plan.error_message is None

    def test_plan_record_state_choices(self, user, permissions, sample_plan_json):
        """Test valid state values."""
        plan = PlanRecord.objects.create(
            plan_json=sample_plan_json,
            created_by=user,
            permissions=permissions,
        )

        # Test all valid states
        for state, label in PlanRecord.STATE_CHOICES:
            plan.state = state
            plan.save()
            assert plan.state == state

    def test_is_complete_property(self, user, permissions, sample_plan_json):
        """Test is_complete property for different states."""
        plan = PlanRecord.objects.create(
            plan_json=sample_plan_json,
            created_by=user,
            permissions=permissions,
        )

        # Pending - not complete
        plan.state = PlanRecord.PENDING
        assert not plan.is_complete

        # Running - not complete
        plan.state = PlanRecord.RUNNING
        assert not plan.is_complete

        # Success - complete
        plan.state = PlanRecord.SUCCESS
        assert plan.is_complete

        # Failure - complete
        plan.state = PlanRecord.FAILURE
        assert plan.is_complete

    def test_is_running_property(self, user, permissions, sample_plan_json):
        """Test is_running property."""
        plan = PlanRecord.objects.create(
            plan_json=sample_plan_json,
            created_by=user,
            permissions=permissions,
        )

        plan.state = PlanRecord.PENDING
        assert not plan.is_running

        plan.state = PlanRecord.RUNNING
        assert plan.is_running

        plan.state = PlanRecord.SUCCESS
        assert not plan.is_running

    def test_get_completed_node_keys(self, settings, user, permissions, sample_plan_json):
        """Test get_completed_node_keys returns successful node keys."""
        settings.DELETE_EXISTING_FILES = True

        plan = PlanRecord.objects.create(
            plan_json=sample_plan_json,
            created_by=user,
            permissions=permissions,
        )

        # Create some WorkflowResults linked to this plan
        topo = Topography1DFactory()
        func = Workflow.objects.get(name="topobank.testing.test")

        # Successful result
        result1 = TopographyAnalysisFactory(
            subject_topography=topo,
            function=func,
            task_state=WorkflowResult.SUCCESS,
        )
        result1.plan = plan
        result1.node_key = "node-1"
        result1.save()

        # Pending result
        result2 = TopographyAnalysisFactory(
            subject_topography=topo,
            function=func,
            task_state=WorkflowResult.PENDING,
        )
        result2.plan = plan
        result2.node_key = "node-2"
        result2.save()

        # Failed result
        result3 = TopographyAnalysisFactory(
            subject_topography=topo,
            function=func,
            task_state=WorkflowResult.FAILURE,
        )
        result3.plan = plan
        result3.node_key = "node-3"
        result3.save()

        completed = plan.get_completed_node_keys()
        assert completed == {"node-1"}

    def test_get_failed_node_keys(self, settings, user, permissions, sample_plan_json):
        """Test get_failed_node_keys returns failed node keys."""
        settings.DELETE_EXISTING_FILES = True

        plan = PlanRecord.objects.create(
            plan_json=sample_plan_json,
            created_by=user,
            permissions=permissions,
        )

        topo = Topography1DFactory()
        func = Workflow.objects.get(name="topobank.testing.test")

        # Failed result
        result = TopographyAnalysisFactory(
            subject_topography=topo,
            function=func,
            task_state=WorkflowResult.FAILURE,
        )
        result.plan = plan
        result.node_key = "failed-node"
        result.save()

        failed = plan.get_failed_node_keys()
        assert failed == {"failed-node"}

    def test_plan_record_str(self, user, permissions, sample_plan_json):
        """Test string representation."""
        plan = PlanRecord.objects.create(
            plan_json=sample_plan_json,
            created_by=user,
            permissions=permissions,
        )

        assert str(plan) == f"PlanRecord {plan.id} (pending)"

        plan.state = PlanRecord.SUCCESS
        plan.save()
        assert str(plan) == f"PlanRecord {plan.id} (success)"


@pytest.mark.django_db
class TestWorkflowResultPlanFields:
    """Tests for plan and node_key fields on WorkflowResult."""

    def test_workflow_result_with_plan(self, settings, user, permissions, sample_plan_json):
        """Test WorkflowResult can be linked to a PlanRecord."""
        settings.DELETE_EXISTING_FILES = True

        plan = PlanRecord.objects.create(
            plan_json=sample_plan_json,
            created_by=user,
            permissions=permissions,
        )

        topo = Topography1DFactory()
        func = Workflow.objects.get(name="topobank.testing.test")

        result = TopographyAnalysisFactory(
            subject_topography=topo,
            function=func,
        )
        result.plan = plan
        result.node_key = "test-node-key"
        result.save()

        # Reload and verify
        result.refresh_from_db()
        assert result.plan == plan
        assert result.node_key == "test-node-key"

    def test_workflow_result_without_plan(self, settings):
        """Test WorkflowResult works without plan (backward compatibility)."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        func = Workflow.objects.get(name="topobank.testing.test")

        result = TopographyAnalysisFactory(
            subject_topography=topo,
            function=func,
        )

        assert result.plan is None
        assert result.node_key is None

    def test_plan_results_relation(self, settings, user, permissions, sample_plan_json):
        """Test PlanRecord.results reverse relation."""
        settings.DELETE_EXISTING_FILES = True

        plan = PlanRecord.objects.create(
            plan_json=sample_plan_json,
            created_by=user,
            permissions=permissions,
        )

        topo = Topography1DFactory()
        func = Workflow.objects.get(name="topobank.testing.test")

        result1 = TopographyAnalysisFactory(subject_topography=topo, function=func)
        result1.plan = plan
        result1.node_key = "node-1"
        result1.save()

        result2 = TopographyAnalysisFactory(subject_topography=topo, function=func)
        result2.plan = plan
        result2.node_key = "node-2"
        result2.save()

        assert plan.results.count() == 2
        assert set(plan.results.values_list("node_key", flat=True)) == {"node-1", "node-2"}
