"""Tests for PlanExecutor."""

from unittest.mock import MagicMock, patch

import pytest
from muflows import WorkflowNode, WorkflowPlan

from topobank.analysis.backends import CeleryBackend
from topobank.analysis.executor import PlanExecutor
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
def mock_backend():
    """Create a mock CeleryBackend."""
    import uuid
    backend = MagicMock(spec=CeleryBackend)
    backend.submit.return_value = str(uuid.uuid4())  # Valid UUID
    return backend


def create_simple_plan():
    """Create a simple single-node WorkflowPlan."""
    node = WorkflowNode(
        key="node-1",
        function="topobank.testing.test",
        subject_key="topography:1",
        kwargs={},
        storage_prefix="data-lake/results/test/abc123",
        depends_on=[],
        depended_on_by=[],
        output_files=["result.json"],
        cached=False,
        analysis_id=None,
    )
    return WorkflowPlan(nodes={"node-1": node}, root_key="node-1")


def create_two_node_plan():
    """Create a plan with two nodes: dep -> root."""
    dep_node = WorkflowNode(
        key="dep-node",
        function="topobank.testing.test",
        subject_key="topography:1",
        kwargs={"type": "dep"},
        storage_prefix="data-lake/results/test/dep",
        depends_on=[],
        depended_on_by=["root-node"],
        output_files=["result.json"],
        cached=False,
        analysis_id=None,
    )
    root_node = WorkflowNode(
        key="root-node",
        function="topobank.testing.test",
        subject_key="topography:1",
        kwargs={"type": "root"},
        storage_prefix="data-lake/results/test/root",
        depends_on=["dep-node"],
        depended_on_by=[],
        output_files=["result.json"],
        cached=False,
        analysis_id=None,
    )
    return WorkflowPlan(
        nodes={"dep-node": dep_node, "root-node": root_node},
        root_key="root-node",
    )


@pytest.mark.django_db
class TestPlanExecutor:
    """Tests for PlanExecutor class."""

    def test_executor_init(self, mock_backend):
        """Test executor initialization."""
        executor = PlanExecutor(mock_backend)
        assert executor.backend == mock_backend

    def test_start_submits_leaf_nodes(self, settings, user, permissions, mock_backend, sync_analysis_functions):
        """Test that start() submits leaf nodes."""
        settings.DELETE_EXISTING_FILES = True

        # Create plan and plan record
        plan = create_simple_plan()
        plan_record = PlanRecord.objects.create(
            plan_json=plan.to_dict(),
            created_by=user,
            permissions=permissions,
        )

        # Create the WorkflowResult for the node
        topo = Topography1DFactory()
        func = Workflow.objects.get(name="topobank.testing.test")
        result = TopographyAnalysisFactory(
            subject_topography=topo,
            function=func,
        )
        result.plan = plan_record
        result.node_key = "node-1"
        result.save()

        # Update plan with analysis_id
        plan.nodes["node-1"].analysis_id = result.id

        # Start execution
        executor = PlanExecutor(mock_backend)
        executor.start(plan, plan_record)

        # Verify plan state updated
        plan_record.refresh_from_db()
        assert plan_record.state == PlanRecord.RUNNING
        assert plan_record.started_at is not None

        # Verify submit was called
        mock_backend.submit.assert_called_once()
        call_args = mock_backend.submit.call_args
        assert call_args[0][0] == result.id  # analysis_id

    def test_start_skips_cached_nodes(self, settings, user, permissions, mock_backend):
        """Test that start() doesn't submit cached nodes."""
        settings.DELETE_EXISTING_FILES = True

        # Create plan with cached node
        plan = create_simple_plan()
        plan.nodes["node-1"].cached = True
        plan.nodes["node-1"].analysis_id = 999

        plan_record = PlanRecord.objects.create(
            plan_json=plan.to_dict(),
            created_by=user,
            permissions=permissions,
        )

        # Start execution
        executor = PlanExecutor(mock_backend)
        executor.start(plan, plan_record)

        # Verify submit was NOT called (node is cached)
        mock_backend.submit.assert_not_called()

    def test_on_node_complete_submits_dependents(
        self, settings, user, permissions, mock_backend, sync_analysis_functions
    ):
        """Test that on_node_complete() submits newly-ready dependent nodes."""
        settings.DELETE_EXISTING_FILES = True

        # Create two-node plan
        plan = create_two_node_plan()
        plan_record = PlanRecord.objects.create(
            plan_json=plan.to_dict(),
            state=PlanRecord.RUNNING,
            created_by=user,
            permissions=permissions,
        )

        # Create WorkflowResults for both nodes
        topo = Topography1DFactory()
        func = Workflow.objects.get(name="topobank.testing.test")

        dep_result = TopographyAnalysisFactory(
            subject_topography=topo,
            function=func,
            task_state=WorkflowResult.SUCCESS,
        )
        dep_result.plan = plan_record
        dep_result.node_key = "dep-node"
        dep_result.save()

        root_result = TopographyAnalysisFactory(
            subject_topography=topo,
            function=func,
            task_state=WorkflowResult.PENDING,
        )
        root_result.plan = plan_record
        root_result.node_key = "root-node"
        root_result.save()

        plan.nodes["dep-node"].analysis_id = dep_result.id
        plan.nodes["root-node"].analysis_id = root_result.id

        # Complete the dependency node
        executor = PlanExecutor(mock_backend)
        executor.on_node_complete(plan, plan_record, "dep-node")

        # Verify root node was submitted
        mock_backend.submit.assert_called_once()
        call_args = mock_backend.submit.call_args
        assert call_args[0][0] == root_result.id

    def test_on_node_complete_marks_plan_success(
        self, settings, user, permissions, mock_backend, sync_analysis_functions
    ):
        """Test that completing root node marks plan as successful."""
        settings.DELETE_EXISTING_FILES = True

        plan = create_simple_plan()
        plan_record = PlanRecord.objects.create(
            plan_json=plan.to_dict(),
            state=PlanRecord.RUNNING,
            created_by=user,
            permissions=permissions,
        )

        # Create successful result
        topo = Topography1DFactory()
        func = Workflow.objects.get(name="topobank.testing.test")
        result = TopographyAnalysisFactory(
            subject_topography=topo,
            function=func,
            task_state=WorkflowResult.SUCCESS,
        )
        result.plan = plan_record
        result.node_key = "node-1"
        result.save()

        # Complete the root node
        executor = PlanExecutor(mock_backend)
        executor.on_node_complete(plan, plan_record, "node-1")

        # Verify plan marked as success
        plan_record.refresh_from_db()
        assert plan_record.state == PlanRecord.SUCCESS
        assert plan_record.completed_at is not None

    def test_on_node_failure_marks_plan_failed(
        self, settings, user, permissions, mock_backend
    ):
        """Test that on_node_failure() marks plan as failed."""
        settings.DELETE_EXISTING_FILES = True

        plan = create_simple_plan()
        plan_record = PlanRecord.objects.create(
            plan_json=plan.to_dict(),
            state=PlanRecord.RUNNING,
            created_by=user,
            permissions=permissions,
        )

        # Report failure
        executor = PlanExecutor(mock_backend)
        executor.on_node_failure(plan, plan_record, "node-1", "Something went wrong")

        # Verify plan marked as failure
        plan_record.refresh_from_db()
        assert plan_record.state == PlanRecord.FAILURE
        assert plan_record.completed_at is not None
        assert "node-1" in plan_record.error_message
        assert "Something went wrong" in plan_record.error_message

    def test_on_node_complete_skips_already_running(
        self, settings, user, permissions, mock_backend, sync_analysis_functions
    ):
        """Test that on_node_complete() doesn't resubmit running nodes."""
        settings.DELETE_EXISTING_FILES = True

        plan = create_two_node_plan()
        plan_record = PlanRecord.objects.create(
            plan_json=plan.to_dict(),
            state=PlanRecord.RUNNING,
            created_by=user,
            permissions=permissions,
        )

        topo = Topography1DFactory()
        func = Workflow.objects.get(name="topobank.testing.test")

        # Dep is complete
        dep_result = TopographyAnalysisFactory(
            subject_topography=topo,
            function=func,
            task_state=WorkflowResult.SUCCESS,
        )
        dep_result.plan = plan_record
        dep_result.node_key = "dep-node"
        dep_result.save()

        # Root is already STARTED
        root_result = TopographyAnalysisFactory(
            subject_topography=topo,
            function=func,
            task_state=WorkflowResult.STARTED,
        )
        root_result.plan = plan_record
        root_result.node_key = "root-node"
        root_result.save()

        plan.nodes["dep-node"].analysis_id = dep_result.id
        plan.nodes["root-node"].analysis_id = root_result.id

        # Complete dep node
        executor = PlanExecutor(mock_backend)
        executor.on_node_complete(plan, plan_record, "dep-node")

        # Root should NOT be submitted again (already running)
        mock_backend.submit.assert_not_called()


@pytest.mark.django_db
class TestCeleryBackend:
    """Tests for CeleryBackend class."""

    def test_submit_calls_apply_async(self, settings):
        """Test that submit() calls Celery apply_async."""
        settings.DELETE_EXISTING_FILES = True

        with patch("topobank.analysis.tasks.execute_workflow_node") as mock_task:
            mock_result = MagicMock()
            mock_result.id = "celery-task-id"
            mock_task.apply_async.return_value = mock_result

            backend = CeleryBackend()
            task_id = backend.submit(123, {"queue": "test-queue"})

            assert task_id == "celery-task-id"
            mock_task.apply_async.assert_called_once_with(
                args=[123],
                queue="test-queue",
            )

    def test_cancel_calls_revoke(self):
        """Test that cancel() calls Celery revoke."""
        with patch("topobank.taskapp.celeryapp.app") as mock_app:
            backend = CeleryBackend()
            backend.cancel("task-123")

            mock_app.control.revoke.assert_called_once_with("task-123", terminate=True)

    def test_get_state_returns_async_result_state(self):
        """Test that get_state() returns AsyncResult state."""
        with patch("celery.result.AsyncResult") as mock_async_result:
            mock_instance = MagicMock()
            mock_instance.state = "SUCCESS"
            mock_async_result.return_value = mock_instance

            backend = CeleryBackend()
            state = backend.get_state("task-123")

            assert state == "SUCCESS"
            mock_async_result.assert_called_once_with("task-123")
