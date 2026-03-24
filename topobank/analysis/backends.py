"""Execution backends for dispatching workflow nodes.

This module provides Django/Celery-specific backends that implement the
ExecutionBackend protocol from muflow, plus a BackendRouter for routing
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
from typing import Dict, Optional, Union

from django.conf import settings
from muflow.executor import ExecutionPayload

_log = logging.getLogger(__name__)


class CeleryBackend:
    """ExecutionBackend that dispatches workflow nodes via Celery.

    This backend submits workflow nodes as Celery tasks, allowing distributed
    execution across worker processes. Since Celery workers have database access,
    they look up workflow details from the WorkflowResult model using the
    analysis_id. The ExecutionPayload is only used for queue routing.

    Example
    -------
    >>> from muflow.executor import ExecutionPayload
    >>> backend = CeleryBackend()
    >>> payload = ExecutionPayload(
    ...     workflow_name="my.workflow",
    ...     kwargs={},
    ...     storage_prefix="results/...",
    ...     queue="analysis",
    ... )
    >>> task_id = backend.submit(analysis_id=123, payload=payload)
    >>> state = backend.get_state(task_id)
    """

    def submit(
        self, analysis_id: int, payload: Union[ExecutionPayload, dict]
    ) -> str:
        """Submit a workflow node for execution.

        Parameters
        ----------
        analysis_id : int
            ID of the WorkflowResult to execute.
        payload : ExecutionPayload or dict
            Execution payload. For Celery, only the queue field is used
            since the worker looks up all other details from the database.
            Dict is supported for backward compatibility.

        Returns
        -------
        str
            Celery task ID.
        """
        from topobank.analysis.tasks import execute_workflow_node

        # Extract queue from ExecutionPayload or dict
        if hasattr(payload, "queue"):
            # ExecutionPayload
            queue = payload.queue
        else:
            # Legacy dict format
            queue = payload.get("queue") or payload.get("celery_queue")

        # Fall back to default queue
        if not queue:
            queue = settings.TOPOBANK_ANALYSIS_QUEUE

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
            from muflow import LambdaBackend

            return LambdaBackend(
                function_name=config.get("function_name"),
                bucket=config.get("bucket"),
            )
        elif backend_type == "local":
            from muflow import LocalBackend

            return LocalBackend()
        else:
            raise ValueError(f"Unknown backend type: {backend_type}")

    def submit(
        self,
        analysis_id: int,
        payload: ExecutionPayload,
    ) -> str:
        """Submit workflow to appropriate backend.

        Parameters
        ----------
        analysis_id : int
            ID of the WorkflowResult to execute.
        payload : ExecutionPayload
            Workflow execution payload. The queue field determines routing.

        Returns
        -------
        str
            Backend-specific task ID.
        """
        queue_name = payload.queue or "default"
        backend = self.get_backend(queue_name)
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


class DjangoCeleryBackend:
    """Django wrapper around muFlow's database-agnostic CeleryBackend.

    This backend wraps muFlow's CeleryBackend to provide Django integration:
    - Builds ExecutionPayload from Django models (handled by caller)
    - Sets up completion callbacks that update WorkflowResult in the database

    This enables a migration path from the existing DB-coupled CeleryBackend
    to the new database-agnostic execution model where Celery workers use
    S3WorkflowContext instead of Django ORM.

    Parameters
    ----------
    bucket : str, optional
        S3 bucket for workflow I/O. If not provided, uses
        settings.AWS_STORAGE_BUCKET_NAME.
    callback_queue : str
        Queue for completion callbacks. Defaults to "callbacks".

    Example
    -------
    >>> from muflow import ExecutionPayload
    >>> backend = DjangoCeleryBackend()
    >>> payload = ExecutionPayload(
    ...     workflow_name="sds_ml.v3.gpr.training",
    ...     kwargs={"threshold": 0.5},
    ...     storage_prefix="muflow/gpr/abc123",
    ...     allowed_outputs={"result.json", "model.nc"},
    ... )
    >>> task_id = backend.submit(analysis_id=123, payload=payload)
    """

    def __init__(
        self,
        bucket: Optional[str] = None,
        callback_queue: str = "callbacks",
    ):
        from muflow.backends.callbacks import CeleryCompletionCallback
        from muflow.backends.celery_backend import CeleryBackend as MuflowCeleryBackend

        from topobank.taskapp.celeryapp import app

        if bucket is None:
            bucket = settings.AWS_STORAGE_BUCKET_NAME

        # Set up completion callback to update Django models
        self._callback = CeleryCompletionCallback(
            celery_app=app,
            task_name="topobank.analysis.tasks.on_workflow_complete",
            queue=callback_queue,
        )

        self._backend = MuflowCeleryBackend(
            celery_app=app,
            bucket=bucket,
            default_queue=getattr(settings, "TOPOBANK_ANALYSIS_QUEUE", "celery"),
        )

    def submit(
        self, analysis_id: int, payload: Union[ExecutionPayload, dict]
    ) -> str:
        """Submit a workflow for database-agnostic execution.

        Parameters
        ----------
        analysis_id : int
            ID of the WorkflowResult to execute.
        payload : ExecutionPayload
            Complete execution payload with all data needed for execution.

        Returns
        -------
        str
            Celery task ID.
        """
        return self._backend.submit(analysis_id, payload)

    def cancel(self, task_id: str) -> None:
        """Cancel a running task.

        Parameters
        ----------
        task_id : str
            Celery task ID to cancel.
        """
        self._backend.cancel(task_id)

    def get_state(self, task_id: str) -> str:
        """Get the state of a task.

        Parameters
        ----------
        task_id : str
            Celery task ID.

        Returns
        -------
        str
            Task state.
        """
        return self._backend.get_state(task_id)
