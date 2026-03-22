"""Execution backends for dispatching workflow nodes.

This module provides Django/Celery-specific backends that implement the
ExecutionBackend protocol from muflows.
"""

from __future__ import annotations

import logging

from django.conf import settings

_log = logging.getLogger(__name__)


class CeleryBackend:
    """ExecutionBackend that dispatches workflow nodes via Celery.

    This backend submits workflow nodes as Celery tasks, allowing distributed
    execution across worker processes.

    Example
    -------
    >>> backend = CeleryBackend()
    >>> task_id = backend.submit(analysis_id=123, payload={"queue": "analysis"})
    >>> state = backend.get_state(task_id)
    """

    def submit(self, analysis_id: int, payload: dict) -> str:
        """Submit a workflow node for execution.

        Parameters
        ----------
        analysis_id : int
            ID of the WorkflowResult to execute.
        payload : dict
            Execution payload containing:
            - queue: Celery queue name (optional, defaults to analysis queue)

        Returns
        -------
        str
            Celery task ID.
        """
        from topobank.analysis.tasks import execute_workflow_node

        queue = payload.get("queue", settings.TOPOBANK_ANALYSIS_QUEUE)
        result = execute_workflow_node.apply_async(
            args=[analysis_id],
            queue=queue,
        )
        _log.debug(f"Submitted task {result.id} for analysis {analysis_id} to queue {queue}")
        return result.id

    def cancel(self, task_id: str) -> None:
        """Cancel a running task.

        Parameters
        ----------
        task_id : str
            Celery task ID to cancel.
        """
        from topobank.taskapp.celeryapp import app

        app.control.revoke(task_id, terminate=True)
        _log.debug(f"Cancelled task {task_id}")

    def get_state(self, task_id: str) -> str:
        """Get the state of a task.

        Parameters
        ----------
        task_id : str
            Celery task ID.

        Returns
        -------
        str
            Task state (PENDING, STARTED, SUCCESS, FAILURE, etc.)
        """
        from celery.result import AsyncResult

        return AsyncResult(task_id).state


def get_configured_backend() -> CeleryBackend:
    """Get the configured execution backend.

    Currently returns CeleryBackend. In the future, this could read from
    settings to return LambdaBackend or BatchBackend.

    Returns
    -------
    CeleryBackend
        The configured execution backend.
    """
    # Future: check settings.TOPOBANK_WORKFLOW_BACKEND
    return CeleryBackend()
