"""Execution backends for dispatching workflow nodes.

This module provides Django/Celery-specific backends that implement the
ExecutionBackend protocol from muflows, plus a BackendRouter for routing
workflows to appropriate backends based on queue configuration.

Queue Configuration
-------------------
Queues are configured in Django settings via WORKFLOW_QUEUES:

    WORKFLOW_QUEUES = {
        "default": {
            "backend": "celery",
            "celery_queue": "analysis",
        },
        "prediction": {
            "backend": "celery",
            "celery_queue": "prediction",
        },
        "training": {
            "backend": "batch",
            "job_definition": "ml-training",
            "job_queue": "ml-queue",
        },
    }

Each workflow declares its queue in Meta.queue, and the router dispatches
to the appropriate backend.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

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
            - queue: Celery queue name (preferred)
            - celery_queue: Celery queue name (deprecated, for backward compatibility)

        Returns
        -------
        str
            Celery task ID.
        """
        from topobank.analysis.tasks import execute_workflow_node

        # Accept both 'queue' (new) and 'celery_queue' (legacy) keys
        queue = payload.get("queue") or payload.get("celery_queue", settings.TOPOBANK_ANALYSIS_QUEUE)
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


class BackendRouter:
    """Routes workflows to appropriate backends based on queue configuration.

    The router reads queue configuration from settings.WORKFLOW_QUEUES and
    creates/caches backend instances as needed.

    Example
    -------
    >>> router = BackendRouter()
    >>> task_id = router.submit(analysis_id=123, queue_name="prediction")
    """

    def __init__(self, queue_config: Optional[Dict] = None):
        """Initialize the router.

        Parameters
        ----------
        queue_config : dict, optional
            Queue configuration mapping. If not provided, reads from
            settings.WORKFLOW_QUEUES.
        """
        if queue_config is None:
            queue_config = getattr(settings, "WORKFLOW_QUEUES", {})

        # Ensure there's always a default queue
        if "default" not in queue_config:
            queue_config["default"] = {
                "backend": "celery",
                "celery_queue": getattr(settings, "TOPOBANK_ANALYSIS_QUEUE", "celery"),
            }

        self._config = queue_config
        self._backends: Dict[str, object] = {}

    def get_queue_config(self, queue_name: str) -> dict:
        """Get configuration for a queue.

        Parameters
        ----------
        queue_name : str
            Queue name.

        Returns
        -------
        dict
            Queue configuration. Falls back to "default" if queue not found.
        """
        return self._config.get(queue_name, self._config["default"])

    def get_backend(self, queue_name: str) -> object:
        """Get or create backend for the given queue.

        Parameters
        ----------
        queue_name : str
            Queue name.

        Returns
        -------
        ExecutionBackend
            Backend instance for this queue.
        """
        config = self.get_queue_config(queue_name)
        backend_type = config.get("backend", "celery")

        # Cache backends by type (not queue) since they're stateless
        if backend_type not in self._backends:
            self._backends[backend_type] = self._create_backend(backend_type, config)

        return self._backends[backend_type]

    def _create_backend(self, backend_type: str, config: dict) -> object:
        """Create a backend instance.

        Parameters
        ----------
        backend_type : str
            Backend type: "celery", "lambda", "batch", "local".
        config : dict
            Backend configuration.

        Returns
        -------
        ExecutionBackend
            Backend instance.
        """
        if backend_type == "celery":
            return CeleryBackend()
        elif backend_type == "lambda":
            from muflows import LambdaBackend

            return LambdaBackend(
                function_name=config.get("function_name"),
                region=config.get("region"),
            )
        elif backend_type == "local":
            from muflows import LocalBackend

            return LocalBackend()
        else:
            raise ValueError(f"Unknown backend type: {backend_type}")

    def submit(self, analysis_id: int, queue_name: str) -> str:
        """Submit workflow to appropriate backend.

        Parameters
        ----------
        analysis_id : int
            ID of the WorkflowResult to execute.
        queue_name : str
            Queue name from workflow's Meta.queue.

        Returns
        -------
        str
            Backend-specific task ID.
        """
        backend = self.get_backend(queue_name)
        config = self.get_queue_config(queue_name)

        # Build payload with queue-specific config
        payload = dict(config)  # Copy config
        payload.pop("backend", None)  # Remove backend type from payload

        return backend.submit(analysis_id, payload)

    def cancel(self, task_id: str, queue_name: str) -> None:
        """Cancel a task.

        Parameters
        ----------
        task_id : str
            Task ID to cancel.
        queue_name : str
            Queue the task was submitted to.
        """
        backend = self.get_backend(queue_name)
        backend.cancel(task_id)

    def get_state(self, task_id: str, queue_name: str) -> str:
        """Get task state.

        Parameters
        ----------
        task_id : str
            Task ID.
        queue_name : str
            Queue the task was submitted to.

        Returns
        -------
        str
            Task state.
        """
        backend = self.get_backend(queue_name)
        return backend.get_state(task_id)


# Global router instance
_router: Optional[BackendRouter] = None


def get_router() -> BackendRouter:
    """Get the global BackendRouter instance.

    Creates the router on first call, reading configuration from settings.

    Returns
    -------
    BackendRouter
        The global router instance.
    """
    global _router
    if _router is None:
        _router = BackendRouter()
    return _router


def get_configured_backend() -> CeleryBackend:
    """Get the default execution backend.

    DEPRECATED: Use get_router().get_backend(queue_name) instead.

    Returns
    -------
    CeleryBackend
        The default Celery backend.
    """
    return CeleryBackend()
