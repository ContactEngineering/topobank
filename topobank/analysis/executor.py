"""Plan execution: walks the DAG and submits ready nodes.

The PlanExecutor coordinates execution of a WorkflowPlan by:
1. Starting leaf nodes (those with no dependencies)
2. Submitting dependent nodes as their dependencies complete
3. Tracking plan completion and failure states
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.utils import timezone
from muflows import WorkflowPlan

if TYPE_CHECKING:
    from topobank.analysis.backends import CeleryBackend
    from topobank.analysis.models import PlanRecord, WorkflowResult

_log = logging.getLogger(__name__)


class PlanExecutor:
    """Walks the DAG, submitting nodes as dependencies complete.

    The executor maintains no state itself - all state is stored in the database
    (PlanRecord and WorkflowResult). This allows execution to resume after
    worker restarts.

    Example
    -------
    >>> executor = PlanExecutor(backend)
    >>> executor.start(plan, plan_record)  # Submits leaf nodes
    >>> # ... later, when a node completes ...
    >>> executor.on_node_complete(plan, plan_record, "completed-node-key")
    """

    def __init__(self, backend: "CeleryBackend"):
        """Initialize the executor.

        Parameters
        ----------
        backend : CeleryBackend
            Backend for submitting tasks.
        """
        self.backend = backend

    def start(self, plan: WorkflowPlan, plan_record: "PlanRecord") -> None:
        """Start plan execution by submitting all leaf nodes.

        Parameters
        ----------
        plan : WorkflowPlan
            The execution plan.
        plan_record : PlanRecord
            Database record for this plan.
        """
        _log.info(f"Starting execution of plan {plan_record.id}")

        # Mark plan as running
        plan_record.state = plan_record.RUNNING
        plan_record.started_at = timezone.now()
        plan_record.save(update_fields=["state", "started_at"])

        # Get already-completed nodes (cached results)
        completed = set()
        for node in plan.nodes.values():
            if node.cached:
                completed.add(node.key)

        # Submit leaf nodes (or nodes whose deps are all cached)
        ready_nodes = plan.ready_nodes(completed)
        _log.debug(f"Plan {plan_record.id}: {len(ready_nodes)} nodes ready to start")

        for node in ready_nodes:
            self._submit_node(node, plan_record)

    def on_node_complete(
        self,
        plan: WorkflowPlan,
        plan_record: "PlanRecord",
        completed_key: str,
    ) -> None:
        """Handle completion of a workflow node.

        Called when any node finishes successfully. Submits newly-ready
        dependent nodes and checks for plan completion.

        Parameters
        ----------
        plan : WorkflowPlan
            The execution plan.
        plan_record : PlanRecord
            Database record for this plan.
        completed_key : str
            Key of the node that just completed.
        """
        _log.debug(f"Plan {plan_record.id}: node {completed_key} completed")

        # Get all completed nodes
        completed = plan_record.get_completed_node_keys()
        completed.add(completed_key)

        # Add cached nodes
        for node in plan.nodes.values():
            if node.cached:
                completed.add(node.key)

        # Check if this was the root node
        if completed_key == plan.root_key:
            self._mark_plan_success(plan_record)
            return

        # Submit newly-ready nodes
        ready_nodes = plan.ready_nodes(completed)
        _log.debug(f"Plan {plan_record.id}: {len(ready_nodes)} nodes newly ready")

        for node in ready_nodes:
            # Check if node is already running or complete
            existing = WorkflowResult.objects.filter(
                plan=plan_record,
                node_key=node.key,
            ).first()

            if existing and existing.task_state in [
                WorkflowResult.PENDING,
                WorkflowResult.STARTED,
                WorkflowResult.SUCCESS,
            ]:
                _log.debug(f"Skipping node {node.key} - already {existing.task_state}")
                continue

            self._submit_node(node, plan_record)

    def on_node_failure(
        self,
        plan: WorkflowPlan,
        plan_record: "PlanRecord",
        failed_key: str,
        error_message: str,
    ) -> None:
        """Handle failure of a workflow node.

        Marks the plan as failed since we don't support partial completion.

        Parameters
        ----------
        plan : WorkflowPlan
            The execution plan.
        plan_record : PlanRecord
            Database record for this plan.
        failed_key : str
            Key of the node that failed.
        error_message : str
            Error message from the failed node.
        """
        _log.error(f"Plan {plan_record.id}: node {failed_key} failed: {error_message}")
        self._mark_plan_failure(plan_record, f"Node {failed_key} failed: {error_message}")

    def _submit_node(self, node, plan_record: "PlanRecord") -> None:
        """Submit a single node for execution.

        Parameters
        ----------
        node : WorkflowNode
            The node to submit.
        plan_record : PlanRecord
            Database record for this plan.
        """
        from topobank.analysis.models import WorkflowResult

        # Get the WorkflowResult for this node
        try:
            analysis = WorkflowResult.objects.get(
                plan=plan_record,
                node_key=node.key,
            )
        except WorkflowResult.DoesNotExist:
            _log.error(f"No WorkflowResult found for node {node.key} in plan {plan_record.id}")
            return

        # Submit to backend
        payload = {"queue": analysis.get_celery_queue()}
        task_id = self.backend.submit(analysis.id, payload)

        # Update task ID
        analysis.task_id = task_id
        analysis.save(update_fields=["task_id"])

        _log.debug(f"Submitted node {node.key} as task {task_id}")

    def _mark_plan_success(self, plan_record: "PlanRecord") -> None:
        """Mark a plan as successfully completed."""
        _log.info(f"Plan {plan_record.id} completed successfully")
        plan_record.state = plan_record.SUCCESS
        plan_record.completed_at = timezone.now()
        plan_record.save(update_fields=["state", "completed_at"])

    def _mark_plan_failure(self, plan_record: "PlanRecord", error_message: str) -> None:
        """Mark a plan as failed."""
        _log.error(f"Plan {plan_record.id} failed: {error_message}")
        plan_record.state = plan_record.FAILURE
        plan_record.completed_at = timezone.now()
        plan_record.error_message = error_message
        plan_record.save(update_fields=["state", "completed_at", "error_message"])
