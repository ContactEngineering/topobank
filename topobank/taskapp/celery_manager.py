"""
The Celery workflow manager: topobank's original execution path behind the
launch API.

Everything Celery-specific about running topobank work lives here or in the
tasks this module dispatches: the two Celery tasks in
:mod:`topobank.analysis.tasks` (``schedule_workflow`` resolves dependencies and
builds a chord, ``execute_workflow`` runs one workflow), the generic
``task_dispatch`` task in :mod:`topobank.taskapp.utils`, the mapping of logical
queue names onto broker queues, and the reading of Celery's result backend when
topobank asks how a run is doing.

The manager keeps its bookkeeping on the row itself: ``task_id`` holds the id of
the Celery task currently responsible for the row and ``launcher_task_id`` the
id of the task that launched a chord of dependencies. Both columns are this
manager's, not part of the launch contract; other managers keep their state in
the handle or elsewhere.
"""

import logging
from decimal import Decimal
from typing import Optional

import celery.states
import pydantic
from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType

from .launch import LaunchHandle, LaunchRequest, RunInfo
from .tasks import ProgressRecorder

_log = logging.getLogger(__name__)


class CeleryWorkflowManager:
    """Run topobank work as Celery tasks. See the module docstring."""

    name = "celery"

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

    # --- launch ------------------------------------------------------------

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

    def launch(self, request: LaunchRequest, instance=None) -> LaunchHandle:
        queue = self.resolve_queue(request.queue)
        options = {"queue": queue} if queue else {}

        if request.kind == "workflow":
            from topobank.analysis.tasks import schedule_workflow

            result = schedule_workflow.apply_async(
                args=[request.pk, request.force], **options
            )
        else:
            from .utils import task_dispatch

            content_type = ContentType.objects.get_by_natural_key(
                request.app_label, request.model_name
            )
            result = task_dispatch.apply_async(
                args=[content_type.id, request.pk] + list(request.args),
                kwargs=request.task_kwargs,
                **options,
            )

        # Record the dispatching task on the row. The tasks overwrite this with
        # their own request id once they run; until then it lets the result
        # backend be consulted for a queued task, and lets the signal handlers
        # find the row should the task die before it ever starts.
        model = apps.get_model(request.app_label, request.model_name)
        model.objects.filter(pk=request.pk).update(task_id=result.id)
        if instance is not None:
            instance.task_id = result.id

        _log.debug(
            "Dispatched %s %s as Celery task %s (queue %s)",
            request.model,
            request.pk,
            result.id,
            queue,
        )
        return LaunchHandle(
            manager=self.name,
            data={"task_id": str(result.id), "model": request.model, "pk": request.pk},
        )

    # --- poll --------------------------------------------------------------

    def _load(self, handle: LaunchHandle):
        model = apps.get_model(*handle.data["model"].split(".", 1))
        return model.objects.get(pk=handle.data["pk"])

    def poll(self, handle: LaunchHandle, instance=None) -> RunInfo:
        if instance is None:
            instance = self._load(handle)

        # Read the result backend once per task: the row's own task and, for a
        # chord of dependencies, its children. Everything below is derived from
        # these two lists so that a poll costs one round trip per task.
        results = instance.get_async_results()
        states = [instance._get_result_state(r) for r in results]
        infos = [instance._get_result_info(r) for r in results]

        # An exception the backend holds for any of the tasks, if there is one
        error = None
        for r, info in zip(results, infos):
            if r and isinstance(info, Exception):
                error = str(info).replace("\x00", "")
                break

        # A failed child fails the row
        if any(state in celery.states.EXCEPTION_STATES for state in states):
            return RunInfo(state=instance.FAILURE, error=error)

        if error is not None:
            # Celery holds an exception but no exception state (e.g. a stored
            # result that *is* the exception); progress is meaningless then
            progress, messages = None, None
        else:
            progress, messages = self._aggregate_progress(states, infos)

        return RunInfo(
            state=self._own_state(instance),
            progress=progress,
            messages=messages,
            error=error,
        )

    def _own_state(self, instance) -> str:
        """The state of the row's own task as Celery's result backend reports it."""
        if instance.task_id is None:
            # Nothing was ever dispatched (or it was reset)
            return instance.NOTRUN
        state = instance._get_result_state(instance.get_async_result())
        # Everything not in the map (e.g. a custom state such as 'PROGRESS') is a
        # running task
        return self.CELERY_STATE_MAP.get(state, instance.STARTED)

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

    def cancel(self, handle: LaunchHandle, instance=None) -> None:
        if instance is None:
            instance = self._load(handle)
        r = instance.get_async_result()
        if r:
            r.revoke()


__all__ = ["CeleryWorkflowManager"]
