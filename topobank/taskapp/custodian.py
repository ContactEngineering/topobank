"""
Reaping of tasks whose worker disappeared.

A row can sit in ``STARTED`` forever, and nothing in the normal task machinery
will ever move it:

``task_acks_late`` is off, so the broker acknowledges a message the moment a
worker *receives* it. If that worker then dies — OOM killer, container restart,
node drain, a forced service update, a broker outage that trips
``worker_cancel_long_running_tasks_on_connection_loss`` — the message is already
gone from the broker, and no ``task_failure`` signal is raised either, because
the process that would have raised it died with the task. The self-reported
state is left at ``STARTED`` and the UI shows a task that has been "running" for
days.

Neither of the two obvious detectors works here:

* **The result backend cannot tell us.** Celery reports ``PENDING`` for a task
  id it has never heard of, and ``_CELERY_STATE_MAP`` maps that to our
  ``PENDING``: "vanished" and "not started yet" are indistinguishable through
  ``AsyncResult``.
* **A duration threshold is the wrong question.** Analyses already carry hard
  and soft time limits (see ``analysis.tasks``), so a task that genuinely runs
  too long fails itself. Anything still ``STARTED`` past that limit has no
  process behind it at all — and picking a cutoff would either kill legitimate
  long runs or leave zombies lying around for hours.

So ask the workers instead. ``inspect()`` reports the task ids that are
executing, reserved or scheduled across the whole fleet. A row in ``STARTED``
whose ``task_id`` no worker knows about is dead by construction: ``STARTED``
means some worker had it and began executing it, so if nobody holds it now,
nobody ever will.

Three guardrails keep that inference honest:

1. If *no* worker replies at all, do nothing. A broker outage or a network
   partition must never be turned into a mass failure.
2. A row must look lost on two consecutive passes before it is failed. This
   covers the small windows where a task is momentarily invisible — between
   finishing and saving its state, or re-queued by a retry.
3. Rows younger than ``min_age`` are never considered, so a task that has just
   been picked up is never a candidate.

Only ``STARTED`` is safe to reap this way. A ``PENDING`` row with a task id may
simply be sitting in the queue: ``inspect`` cannot see messages that no worker
has reserved yet, so those would look lost while being perfectly healthy.
"""

import logging
from datetime import timedelta

from django.apps import apps
from django.core.cache import cache
from django.utils import timezone

from .celeryapp import app
from .models import TaskStateModel

_log = logging.getLogger(__name__)

#: A row must have started at least this long ago to be considered.
DEFAULT_MIN_AGE = timedelta(minutes=15)

#: Where the previous pass's candidates are remembered, for guardrail 2. Losing
#: this (cache eviction, Redis restart) costs one extra pass, nothing more.
SUSPECT_CACHE_KEY = "taskapp-custodian-lost-task-candidates"
SUSPECT_CACHE_SECONDS = 3600

#: Seconds to wait for workers to answer the broadcast. Generous on purpose:
#: a false "nobody knows this task" is what we are trying hard to avoid, and
#: this runs on a schedule where a few seconds cost nothing.
INSPECT_TIMEOUT = 10.0

LOST_TASK_ERROR = (
    "The worker running this task disappeared before it finished (a restarted "
    "container, a lost node, or the task was killed, for instance because it ran "
    "out of memory). No result was produced. Please run it again."
)


def task_state_models():
    """Every concrete model that carries task state."""
    return [
        model
        for model in apps.get_models()
        if issubclass(model, TaskStateModel) and not model._meta.abstract
    ]


def _task_ids_in(reply):
    """Collect task ids from one ``inspect`` reply."""
    ids = set()
    for entries in (reply or {}).values():
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            # `active`/`reserved` report the task directly, `scheduled` wraps it
            # in an eta entry with the task under "request".
            task_id = entry.get("id") or (entry.get("request") or {}).get("id")
            if task_id:
                ids.add(str(task_id))
    return ids


def live_task_ids(timeout=INSPECT_TIMEOUT):
    """
    Task ids the worker fleet currently knows about.

    Returns ``None`` if no worker answered, which callers must treat as "no
    information" rather than "nothing is running".
    """
    inspect = app.control.inspect(timeout=timeout)
    live = set()
    answered = False
    for name in ("active", "reserved", "scheduled"):
        try:
            reply = getattr(inspect, name)()
        except Exception as exc:
            # Deliberately broad: a broker problem surfaces as any of a dozen
            # kombu/redis/socket errors, and every one of them means the same
            # thing here - we did not learn anything and must not act.
            _log.warning("Custodian: could not inspect %s tasks: %s", name, exc)
            return None
        if reply:
            answered = True
            live |= _task_ids_in(reply)
    if not answered:
        return None
    return live


def _propagate_to_parent(obj, error):
    """Fail the parent of a reaped dependency, so it stops waiting for a chord."""
    metadata = getattr(obj, "metadata", None) or {}
    parent_id = metadata.get("parent_workflow_result_id")
    if not parent_id:
        return
    from topobank.analysis.tasks import _fail_parent_on_dependency_failure

    # The helper copies error and traceback off the dependency, so reflect the
    # values we just wrote to the database onto the in-memory instance.
    obj.task_error = error
    obj.task_traceback = None
    _fail_parent_on_dependency_failure(parent_id, obj, "custodian")


def find_lost(live, min_age=DEFAULT_MIN_AGE):
    """Rows in ``STARTED`` whose task no worker knows about."""
    cutoff = timezone.now() - min_age
    lost = []
    for model in task_state_models():
        # Deliberately not deferring columns: `mark_lost` reads `metadata` to
        # find a waiting parent, and a deferred load would turn that into a
        # query per row. In a healthy system this queryset is empty anyway.
        queryset = model.objects.filter(
            task_state=model.STARTED, task_start_time__lt=cutoff
        ).exclude(task_id=None)
        for obj in queryset.iterator():
            if str(obj.task_id) not in live:
                lost.append(obj)
    return lost


def mark_lost(obj, error=LOST_TASK_ERROR):
    """
    Transition one row to FAILURE. Returns whether it was still lost.

    The filtered ``update()`` makes this a no-op if the row reached a terminal
    state in the meantime, so a task that finished between the sweep's two
    passes is never overwritten.
    """
    updated = type(obj).objects.filter(pk=obj.pk, task_state=obj.STARTED).update(
        task_state=obj.FAILURE,
        task_error=error,
        task_end_time=timezone.now(),
    )
    if not updated:
        return False
    _propagate_to_parent(obj, error)
    return True


@app.task
def reap_lost_tasks(
    min_age_minutes=None, require_confirmation=True, dry_run=False
):
    """
    Fail rows whose worker died. Scheduled by Celery beat; see module docstring.

    ``require_confirmation`` implements the two-pass rule and should only be
    turned off for a one-off cleanup of a backlog that is known to be dead.
    """
    min_age = (
        DEFAULT_MIN_AGE
        if min_age_minutes is None
        else timedelta(minutes=int(min_age_minutes))
    )

    live = live_task_ids()
    if live is None:
        _log.warning(
            "Custodian: no Celery worker answered, skipping the lost-task sweep. "
            "Nothing was changed."
        )
        return {"skipped": True, "candidates": 0, "failed": 0}

    candidates = find_lost(live, min_age=min_age)
    candidate_ids = {str(obj.task_id) for obj in candidates}

    if require_confirmation:
        previous = set(cache.get(SUSPECT_CACHE_KEY) or ())
        cache.set(SUSPECT_CACHE_KEY, candidate_ids, SUSPECT_CACHE_SECONDS)
        confirmed = [obj for obj in candidates if str(obj.task_id) in previous]
        if len(confirmed) < len(candidates):
            _log.info(
                "Custodian: %d task(s) look lost for the first time; they will be "
                "failed on the next pass if they still look lost.",
                len(candidates) - len(confirmed),
            )
    else:
        confirmed = candidates

    if dry_run:
        for obj in confirmed:
            _log.info(
                "Custodian: would fail %s %s (task %s)",
                type(obj).__name__,
                obj.pk,
                obj.task_id,
            )
        return {
            "skipped": False,
            "candidates": len(candidates),
            "failed": 0,
            "would_fail": len(confirmed),
        }

    failed = 0
    for obj in confirmed:
        if mark_lost(obj):
            failed += 1
            _log.warning(
                "Custodian: failed %s %s because its worker disappeared "
                "(task %s).",
                type(obj).__name__,
                obj.pk,
                obj.task_id,
            )
    if failed:
        _log.warning("Custodian: failed %d task(s) whose worker disappeared.", failed)
    return {"skipped": False, "candidates": len(candidates), "failed": failed}
