import importlib
import logging
import os
import sys
import time
from datetime import timedelta
from functools import lru_cache
from typing import Optional
from uuid import UUID

from celery.exceptions import Ignore
from celery.utils import uuid
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q, RestrictedError
from django.utils import timezone

from ..settings import defaults
from .celeryapp import app
from .models import Dependency, TaskStateModel, Version

_log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def in_celery_worker_process() -> bool:
    """
    Detect whether we are running within a Celery worker process.

    Uses SERVICE_NAME environment variable if available (preferred, set by docker-compose),
    otherwise falls back to sys.argv inspection.

    Returns
    -------
    bool
        True if running in a Celery worker process, False otherwise.

    Notes
    -----
    This function is cached after first call since the process type doesn't change
    during runtime. The SERVICE_NAME approach is more reliable than sys.argv inspection
    because:
    - It works regardless of how celery is invoked (direct, via python -m, etc.)
    - It's explicitly set in the deployment configuration
    - It's inherited by child processes correctly
    """
    # Preferred: Check SERVICE_NAME environment variable (set in docker-compose.yml)
    service_name = os.environ.get("SERVICE_NAME", "")
    if service_name:
        # celery-analysis, celery-quick are workers; celery-beat is not
        return service_name.startswith("celery-") and "beat" not in service_name

    # Fallback: sys.argv inspection (less reliable)
    # See: https://stackoverflow.com/questions/39003282/how-can-i-detect-whether-im-running-in-a-celery-worker
    return bool(
        sys.argv and sys.argv[0].endswith("celery") and "worker" in sys.argv
    )


PENDING = "pe"
PENDING_DEPENDENCIES = "pd"
STARTED = "st"
RETRY = "re"
FAILURE = "fa"
SUCCESS = "su"
NOTRUN = "no"

TASK_STATE_CHOICES = (
    (PENDING, "pending"),
    (PENDING_DEPENDENCIES, "pending dependencies"),
    (STARTED, "started"),
    (RETRY, "retry"),
    (FAILURE, "failure"),
    (SUCCESS, "success"),
    (NOTRUN, "not run"),
)


class ConfigurationException(Exception):
    pass


def _get_package_version_tuple(pkg_name, version_expr):
    """

    :param pkg_name: name of the package which is used in import statement
    :param version_expr: expression used to get the version from already imported module
    :return: version tuple
    """
    mod = importlib.import_module(pkg_name)

    version = eval(version_expr, {pkg_name: mod})

    version_tuple = version.split(".")

    try:
        major: int = int(version_tuple[0])
    except:  # noqa: E722
        # If the first part is not an integer, we treat the whole string as "extra"
        # and set major/minor/micro to 0. This is to handle cases like NuMPI's
        # git hashes (e.g. f0feec2+dirty).
        return 0, 0, None, version

    try:
        minor: int = int(version_tuple[1])
    except:  # noqa: E722
        minor = 0
        micro = None
        s = f"{version_tuple[0]}"
        try:
            extra: str = version[len(s):]
        except:  # noqa: E722
            extra = None
        return major, minor, micro, extra

    try:
        # because of version strings like '0.51.0+0.g2c488bd.dirty'
        micro: int = int(version_tuple[2].split("+")[0])
        s = f"{version_tuple[0]}.{version_tuple[1]}.{micro}"
    except:  # noqa: E722
        micro = None
        s = f"{version_tuple[0]}.{version_tuple[1]}"

    try:
        extra: str = version[len(s):]  # the rest of the version string
        # Don't strip leading dot if it's followed by dev or other indicators
        # only if it was part of the s string.
        # Actually, let's look at the failing case:
        # version = '1.66.3.dev96+g53c1c0d2.dirty'
        # s = '1.66.3'
        # extra = '.dev96+g53c1c0d2.dirty'
        # result = '1.66.3.dev96+g53c1c0d2.dirty'
        pass
    except:  # noqa: E722
        extra = None

    if extra == "":
        extra = None

    return major, minor, micro, extra


@transaction.atomic(durable=True)
def get_package_version(pkg_name, version_expr):
    """
    Return version instance for currently installed version of a package.
    The function creates the entry in the dependency and version tables if
    they are missing. This serves to track versions of packages that are used
    for generating analysis results.

    Parameters
    ----------
    pkg_name : str
        name of the package which is used in import statement
    version_expr : str
        expression (Python code) used to get the version from already
        imported module

    Returns
    -------
    version : Version
        Instance of the Version class
    """
    major, minor, micro, extra = _get_package_version_tuple(pkg_name, version_expr)

    # create dependency object if it does not yet exist
    dep, created = Dependency.objects.get_or_create(import_name=pkg_name)

    # make sure the current version of the dependency is available in database
    try:
        version, created = Version.objects.get_or_create(
            dependency=dep, major=major, minor=minor, micro=micro, extra=extra
        )
    except Version.MultipleObjectsReturned:
        # Databases written before the unique constraint was fixed can contain
        # duplicate rows for the same version, because PostgreSQL treated the
        # NULL `micro`/`extra` of the old `unique_together` as distinct. The
        # `get()` inside `get_or_create()` then fails and takes every analysis
        # down with it. Settle on the oldest row so that analyses keep running;
        # taskapp migration 0003 merges the duplicates away for good.
        version = (
            Version.objects.filter(
                dependency=dep, major=major, minor=minor, micro=micro, extra=extra
            )
            .order_by("id")
            .first()
        )
        _log.warning(
            "Found duplicate Version rows for %s %s.%s (micro=%s, extra=%s); "
            "using the oldest (id=%s). Run the taskapp migrations to remove the "
            "duplicates.",
            pkg_name,
            major,
            minor,
            micro,
            extra,
            version.id,
        )

    return version


def _reclaim_after(celery_task) -> Optional[float]:
    """Seconds after which a run under ``celery_task``'s id may be taken over.

    ``TOPOBANK_TASK_RECLAIM_AFTER`` when set; otherwise the task's hard time
    limit, past which the worker has killed the run, so that a redelivery of its
    message is the only way the task still gets done. None means never.
    """
    configured = getattr(
        settings,
        "TOPOBANK_TASK_RECLAIM_AFTER",
        defaults.TOPOBANK_TASK_RECLAIM_AFTER,
    )
    if configured is not None:
        return configured
    # Resolved as the worker does: per message, then per task, then globally
    limits = getattr(celery_task.request, "timelimit", None) or (None, None)
    return limits[0] or celery_task.time_limit or celery_task.app.conf.task_time_limit


def claim_started(model, obj_id, task_id, reclaim_after=None):
    """Claim the row behind a delivered message for this worker.

    Moves the row to ``STARTED`` only if it still belongs to ``task_id`` and is
    waiting for a worker: ``PENDING``, or ``NOTRUN`` for a message queued by a
    caller that never persisted the pending state. A row recorded as ``STARTED``
    under the same id is taken over only once its start is older than
    ``reclaim_after`` seconds (never, if None): that is the redelivery of a run
    the worker could not finish, whereas a younger run is alive and the message
    is a duplicate.

    The update is a single conditional statement, so of several deliveries of the
    same message exactly one claims the row. Returns the start time recorded for
    the run if this call claimed it, else None.
    """
    now = timezone.now()
    claimable = Q(task_state__in=(TaskStateModel.PENDING, TaskStateModel.NOTRUN))
    if reclaim_after is not None:
        claimable |= Q(task_state=TaskStateModel.STARTED) & (
            Q(task_start_time__isnull=True)
            | Q(task_start_time__lt=now - timedelta(seconds=reclaim_after))
        )
    claimed = model._base_manager.filter(
        claimable, pk=obj_id, task_id=task_id
    ).update(task_state=TaskStateModel.STARTED, task_start_time=now)
    return now if claimed == 1 else None


# How often, and how long apart, a delivery retries its claim while the row has
# no task id yet. A dispatcher from before claims were introduced sends the
# message first and writes the task id afterwards, so during a rolling upgrade a
# worker can receive a message before the row names it.
CLAIM_RETRIES = 5
CLAIM_RETRY_DELAY = 1.0


def _claim_delivery(model, obj_id, task_id, reclaim_after):
    """`claim_started`, retried while the row still has no task id at all."""
    for attempt in range(CLAIM_RETRIES + 1):
        started_at = claim_started(model, obj_id, task_id, reclaim_after)
        if started_at is not None:
            return started_at
        current = (
            model._base_manager.filter(pk=obj_id)
            .values_list("task_id", flat=True)
            .first()
        )
        if current is not None or attempt == CLAIM_RETRIES:
            return None
        _log.info(
            "task_dispatch: %s id=%s does not name task %s yet; retrying the "
            "claim in %.1f s.",
            model.__name__,
            obj_id,
            task_id,
            CLAIM_RETRY_DELAY,
        )
        time.sleep(CLAIM_RETRY_DELAY)
    return None  # pragma: no cover - the loop returns


@app.task(bind=True)
def task_dispatch(celery_task, cls_id, obj_id, *args, **kwargs):
    ct = ContentType.objects.get_for_id(cls_id)
    model = ct.model_class()
    task_id = celery_task.request.id
    started_at = _claim_delivery(model, obj_id, task_id, _reclaim_after(celery_task))
    if started_at is None:
        # Duplicate delivery of a run that is already under way or finished, or a
        # message superseded by a newer dispatch of the same object, or the object
        # is gone. Either way another delivery owns the work. Ignored rather than
        # returned: a return would record a success for this task id, which the
        # live run still carries.
        _log.info(
            "task_dispatch: not running task %s for %s id=%s; the row is not "
            "waiting for this task (duplicate, superseded or deleted).",
            task_id,
            model.__name__,
            obj_id,
        )
        raise Ignore()
    try:
        obj = ct.get_object_for_this_type(id=obj_id)
    except model.DoesNotExist:
        # Ignore the task if the instance no longer exists
        raise Ignore()
    # The run this delivery claimed. `run_task` compares it with the row it
    # loaded, which a newer dispatch may have claimed in the meantime.
    obj._claimed_run = (str(task_id), started_at)
    if obj.run_task(celery_task, *args, **kwargs) is False:
        raise Ignore()
    # Return True so Celery knows the task completed successfully
    # This is important for tasks that do not return anything
    return True


def claim_pending(
    model_instance: TaskStateModel, *, force: bool = False, from_states=None
) -> Optional[str]:
    """Claim ``model_instance`` for a new dispatch and persist the pending state.

    A single conditional update moves the row to ``PENDING`` under a freshly
    generated task id, unless a task is already in flight (``force=True`` claims
    regardless) or, with ``from_states``, unless the row is in one of those
    states. Of concurrent callers exactly one claims the row; the update runs in
    the caller's transaction, so a rollback releases the claim.

    On success the instance carries the persisted pending state and the new task
    id is returned. Otherwise the instance's task state is reloaded from the
    database, so that a later save of the instance cannot write back a stale
    state, and None is returned.
    """
    if model_instance.pk is None:
        raise ValueError(
            f"Cannot dispatch a task for an unsaved {type(model_instance).__name__}."
        )
    task_id = UUID(uuid())
    values = TaskStateModel.pending_state_values(task_id)
    queryset = type(model_instance)._base_manager.filter(pk=model_instance.pk)
    if from_states is not None:
        queryset = queryset.filter(task_state__in=from_states)
    if not force:
        queryset = queryset.exclude(task_state__in=TaskStateModel.IN_FLIGHT_STATES)
    if queryset.update(**values) != 1:
        try:
            model_instance.refresh_from_db(
                fields=list(TaskStateModel.PENDING_STATE_FIELDS)
            )
        except type(model_instance).DoesNotExist:
            pass
        return None
    for name, value in values.items():
        setattr(model_instance, name, value)
    # The claim is in the database: a later save of the instance has nothing to
    # write for these fields
    model_instance._remember_fields(values)
    return str(task_id)


def submit_on_commit(
    model_instance: TaskStateModel,
    task_id: str,
    celery_queue: Optional[str] = None,
    args=(),
    kwargs=None,
):
    """Send the claimed task ``task_id`` to Celery once the transaction commits.

    The id is passed to the broker, so the worker finds the row it was claimed
    for, and a rollback of the claim cancels the dispatch.
    """
    celery_kwargs = {}
    if celery_queue is not None:
        # Explicit celery queue given
        celery_kwargs["queue"] = celery_queue
    elif hasattr(model_instance, "celery_queue"):
        # Static celery queue
        celery_kwargs["queue"] = model_instance.celery_queue
    elif hasattr(model_instance, "get_celery_queue"):
        # Dynamic celery queue
        celery_kwargs["queue"] = model_instance.get_celery_queue()

    content_type_id = ContentType.objects.get_for_model(model_instance).id
    obj_id = model_instance.pk
    model = type(model_instance)

    def submit_task_to_celery():
        try:
            task_dispatch.apply_async(
                args=[content_type_id, obj_id] + list(args),
                kwargs=kwargs or {},
                task_id=str(task_id),
                **celery_kwargs,
            )
        except Exception as exc:
            # The claim is committed but no message exists for it, and nothing
            # would ever tell: the broker reports an unknown task id as pending.
            # Fail the row, unless a newer dispatch has claimed it meanwhile.
            _log.exception(
                "Could not submit task %s for %s id=%s to the broker.",
                task_id,
                model.__name__,
                obj_id,
            )
            values = {
                "task_state": TaskStateModel.FAILURE,
                "task_end_time": timezone.now(),
                "task_error": f"The task could not be submitted to the broker: {exc}",
            }
            failed = model._base_manager.filter(
                pk=obj_id, task_id=task_id, task_state=TaskStateModel.PENDING
            ).update(**values)
            if failed and str(model_instance.task_id) == str(task_id):
                for name, value in values.items():
                    setattr(model_instance, name, value)
                model_instance._remember_fields(values)
            raise

    transaction.on_commit(submit_task_to_celery)


def run_task(
    model_instance: TaskStateModel,
    celery_queue: Optional[str] = None,
    *args,
    force: bool = False,
    from_states=None,
    **kwargs,
) -> bool:
    """Dispatch the task of ``model_instance`` unless one is already in flight.

    Claims the row (see :func:`claim_pending`), which persists the pending state,
    and submits the task once the surrounding transaction commits. Callers do not
    need to save the instance afterwards. The in-flight guard keys off the
    database, not the instance, so it also holds for stale instances and for
    concurrent callers: it prevents the re-entrant dispatch that happens when
    `refresh_cache` mutates significant fields and its terminal `save()` re-enters
    `run_task`. Pass `force=True` to deliberately re-run an in-flight task (e.g. an operator
    recompute); the run it replaces then discards its results. Pass `from_states`
    to dispatch only while the row is in one of those states, e.g. to process a
    measurement that was never processed without reprocessing one that was.

    Returns whether a task was dispatched.
    """
    task_id = claim_pending(model_instance, force=force, from_states=from_states)
    if task_id is None:
        _log.debug(
            "run_task: skipping dispatch for %s id=%s; task already in-flight "
            "(state=%s). Pass force=True to override.",
            type(model_instance).__name__,
            model_instance.pk,
            model_instance.task_state,
        )
        return False
    submit_on_commit(model_instance, task_id, celery_queue, args, kwargs)
    return True


def delete_tolerating_restrict(queryset, description):
    """Delete the queryset's rows, skipping those protected by a RESTRICT reference.

    Downstream plugins may guard rows with RESTRICT foreign keys (e.g. a
    result a trained model was built from). A bulk delete aborts wholesale on
    the first protected row, so fall back to per-row deletes and leave
    protected rows for a later run, once their guard clears.

    Returns the number of rows that could not be deleted.
    """
    try:
        queryset.delete()
        return 0
    except RestrictedError:
        skipped = 0
        for obj in queryset.iterator():
            try:
                obj.delete()
            except RestrictedError:
                skipped += 1
        if skipped:
            _log.info(
                "Custodian: skipped %d %s protected by RESTRICT references.",
                skipped,
                description,
            )
        return skipped
