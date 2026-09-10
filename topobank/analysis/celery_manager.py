"""
The Celery workflow manager: topobank's original execution path behind the
workflow manager interface.

Everything Celery-specific about running workflows lives here or in the tasks
this module dispatches: the two Celery tasks in :mod:`topobank.analysis.tasks`
(``schedule_workflow`` resolves dependencies and builds a chord,
``execute_workflow`` runs one workflow), the mapping of logical queue names onto
broker queues, and the reading of Celery's result backend when topobank asks how
a run is doing.

Workflows for this manager are
:class:`~topobank.analysis.legacy.workflows.WorkflowImplementation` subclasses,
registered with :data:`registry` (``topobank.analysis.registry.register_implementation``
is an alias). The implementation methods run in-process in a Celery worker.

The manager keeps its bookkeeping on the row itself: ``task_id`` holds the id of
the Celery task currently responsible for the row and ``launcher_task_id`` the
id of the task that launched a chord of dependencies. Both columns are this
manager's, not part of the manager contract.
"""

import logging
from decimal import Decimal
from typing import Optional

import celery.states
import pydantic
from django.conf import settings

from ..taskapp.tasks import ProgressRecorder
from .managers import LaunchHandle, RunInfo, WorkflowRegistry

_log = logging.getLogger(__name__)

#: Workflows the Celery manager can run. Plugins register their
#: `WorkflowImplementation` subclasses here.
registry = WorkflowRegistry()


class CeleryWorkflowManager:
    """Run topobank workflows as Celery tasks. See the module docstring."""

    name = "celery"
    registry = registry

    #: Celery states mapped onto topobank task states. Anything not listed (e.g.
    #: the custom ``PROGRESS`` state) is read as a running task.
    CELERY_STATE_MAP = {
        celery.states.SUCCESS: "su",
        celery.states.STARTED: "st",
        celery.states.PENDING: "pe",
        celery.states.RECEIVED: "pe",
        celery.states.RETRY: "pe",
        # The following are in celery.states.EXCEPTION_STATES
        celery.states.FAILURE: "fa",
        celery.states.REVOKED: "fa",
        celery.states.REJECTED: "fa",
    }

    # --- queues ------------------------------------------------------------

    def resolve_queue(self, queue: Optional[str]) -> Optional[str]:
        """
        Map a logical queue name onto a broker queue.

        Workflow implementations name queues logically (``"analysis"``,
        ``"prediction"``); deployments that prefix or rename their broker queues
        translate them through ``CELERY_LOGICAL_QUEUE_MAP``. Names not in the map
        pass through unchanged.
        """
        if queue is None:
            return None
        return getattr(settings, "CELERY_LOGICAL_QUEUE_MAP", {}).get(queue, queue)

    def queue_for(self, result) -> str:
        """The broker queue a `WorkflowResult` should be dispatched to."""
        implementation = self.registry.get(result.workflow_name)
        queue = getattr(getattr(implementation, "Meta", None), "celery_queue", None)
        if queue is None:
            # Default queue for workflow result tasks
            queue = settings.TOPOBANK_ANALYSIS_QUEUE
        return self.resolve_queue(queue)

    # --- launch ------------------------------------------------------------

    def launch(self, result, *, force: bool = False) -> LaunchHandle:
        from .tasks import schedule_workflow

        task = schedule_workflow.apply_async(
            args=[result.id, force], queue=self.queue_for(result)
        )
        # Record the dispatching task on the row. The tasks overwrite this with
        # their own request id once they run; until then it lets the result
        # backend be consulted for a queued task, and lets the signal handlers
        # find the row should the task die before it ever starts.
        result.task_id = task.id
        result.save(update_fields=["task_id"])
        _log.debug(
            "Dispatched WorkflowResult %s as Celery task %s", result.id, task.id
        )
        return LaunchHandle(manager=self.name, data={"task_id": str(task.id)})

    # --- poll --------------------------------------------------------------

    def poll(self, result) -> RunInfo:
        # Read the result backend once per task: the row's own task and, for a
        # chord of dependencies, its children. Everything below is derived from
        # these two lists so that a poll costs one round trip per task.
        results = result.get_async_results()
        states = [result._get_result_state(r) for r in results]
        infos = [result._get_result_info(r) for r in results]

        # An exception the backend holds for any of the tasks, if there is one
        error = None
        for r, info in zip(results, infos):
            if r and isinstance(info, Exception):
                error = str(info).replace("\x00", "")
                break

        # A failed child fails the row
        if any(state in celery.states.EXCEPTION_STATES for state in states):
            return RunInfo(state=result.FAILURE, error=error)

        if error is not None:
            # Celery holds an exception but no exception state (e.g. a stored
            # result that *is* the exception); progress is meaningless then
            progress, messages = None, None
        else:
            progress, messages = self._aggregate_progress(states, infos)

        return RunInfo(
            state=self._own_state(result),
            progress=progress,
            messages=messages,
            error=error,
        )

    def _own_state(self, result) -> str:
        """The state of the row's own task as Celery's result backend reports it."""
        if result.task_id is None:
            # Nothing was ever dispatched (or it was reset)
            return result.NOTRUN
        state = result._get_result_state(result.get_async_result())
        # Everything not in the map (e.g. a custom state such as 'PROGRESS') is a
        # running task
        return self.CELERY_STATE_MAP.get(state, result.STARTED)

    def _aggregate_progress(self, states, infos):
        """
        Aggregate progress over the row's task and its children.

        Returns ``(percent, messages)``. Finished tasks count as complete,
        pending tasks as not started, and running tasks contribute the progress
        `ProgressRecorder` wrote for them.
        """
        total = 0
        current = 0
        messages = []
        for state, info in zip(states, infos):
            if state == celery.states.SUCCESS:
                total += 1
                current += 1
            elif state == celery.states.PENDING:
                total += 1
            elif info:
                # We assume the state is 'PROGRESS' and `info` is the progress
                # dictionary written by `ProgressRecorder`.
                try:
                    task_progress = ProgressRecorder.Model(**info)
                except (pydantic.ValidationError, TypeError):
                    _log.info(
                        "Progress payload %r is not a valid progress dictionary; "
                        "ignoring it.",
                        info,
                    )
                else:
                    total += 1
                    current += task_progress.current / task_progress.total
                    if task_progress.message is not None:
                        messages.append(task_progress.message)

        percent = 0.0
        if total > 0:
            percent = float(round((Decimal(current) / Decimal(total)) * Decimal(100), 2))
        return percent, messages

    # --- cancel ------------------------------------------------------------

    def cancel(self, result) -> None:
        r = result.get_async_result()
        if r:
            r.revoke()
