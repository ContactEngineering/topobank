"""
The status contract: how a workflow engine reports a run back to topobank.

A :class:`StatusReport` is the only way lifecycle state - task state, error,
traceback, timings, peak memory, produced files - reaches a task-state row. The
Celery engine calls :func:`apply_status_report` from inside its worker; a
engine that runs outside the Django process hands its reports to whatever
topobank code observes it (a poll, a completion event) and that code calls the
same function. Either way, every lifecycle write goes through one place, and
the lifecycle hooks configured in ``TOPOBANK_TASK_LIFECYCLE_HOOKS`` fire from
that one place regardless of the engine.

Files are part of the report, not of storage: an engine that produced output
says which files it wrote (as :class:`FileEntry` items) and topobank turns that
list into `Manifest` rows. topobank never lists a storage prefix to find out
what a run produced; listing object storage is slow and brittle, and the
engine already knows.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

import pydantic
from django.conf import settings
from django.utils import timezone
from django.utils.module_loading import import_string

_log = logging.getLogger(__name__)


class FileEntry(pydantic.BaseModel):
    """
    One file a run produced, as an engine describes it.

    ``path`` is the file's name within the configured Django storage (the
    ``name`` a `FileField` would hold), not a URL. ``size_bytes`` and
    ``content_type`` are optional metadata that saves a storage round trip.
    """

    model_config = pydantic.ConfigDict(extra="forbid")

    filename: str
    path: str
    size_bytes: Optional[int] = None
    content_type: str = ""
    kind: str = "der"


class StatusReport(pydantic.BaseModel):
    """
    An engine's account of a run at some point in its life.

    Only ``state`` is required. Every other field is applied when given and left
    alone when ``None``, so a report can carry as little as a state change or as
    much as the full outcome of a run.
    """

    model_config = pydantic.ConfigDict(extra="forbid")

    #: A :class:`~topobank.taskapp.models.TaskStateModel` state code.
    state: str

    error: Optional[str] = None
    traceback: Optional[str] = None

    #: Peak memory of the run in bytes.
    memory: Optional[int] = None
    #: Per-stage timings, as produced by ``muTimer.Timer.to_dict()``.
    timer: Optional[Dict[str, Any]] = None
    #: DOIs of the methods the run used.
    dois: Optional[List[str]] = None

    #: Files the run produced. Applied on success only.
    files: Optional[List[FileEntry]] = None

    #: When the run started or ended. Filled in by the receiver when omitted.
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


def _terminal_states(instance):
    return (instance.SUCCESS, instance.FAILURE)


def _clean(text: Optional[str]) -> Optional[str]:
    # PostgreSQL text columns reject NUL bytes; tracebacks of crashed C
    # extensions occasionally contain them.
    return None if text is None else text.replace("\x00", "")


def apply_status_report(
    instance,
    report: StatusReport,
    *,
    claim: bool = False,
    extra_fields: Iterable[str] = (),
) -> bool:
    """
    Apply ``report`` to ``instance`` and persist it.

    Parameters
    ----------
    instance : TaskStateModel
        The row the report is about.
    report : StatusReport
        What the engine says about the run.
    claim : bool, optional
        Only for a ``STARTED`` report. When true, the transition is made with a
        conditional update that succeeds for exactly one caller: a row that is
        already running or finished is left alone and ``False`` is returned. A
        worker that loses the claim must not run the work. This closes the
        window in which two workers pick up the same row.
    extra_fields : iterable of str, optional
        Names of fields the caller has set on ``instance`` that should be
        persisted together with the report (e.g. ``"task_id"``).

    Returns
    -------
    bool
        ``True`` if the report was applied, ``False`` if a claim was lost.
    """
    now = timezone.now()
    fields = ["task_state"]
    terminal = report.state in _terminal_states(instance)

    instance.task_state = report.state

    if report.state == instance.STARTED:
        if instance.task_start_time is None or report.start_time is not None:
            instance.task_start_time = report.start_time or now
            fields.append("task_start_time")

    if report.error is not None:
        instance.task_error = _clean(report.error)
        fields.append("task_error")
    if report.traceback is not None:
        instance.task_traceback = _clean(report.traceback)
        fields.append("task_traceback")
    if report.memory is not None:
        instance.task_memory = report.memory
        fields.append("task_memory")
    if report.timer is not None:
        instance.task_timer = report.timer
        fields.append("task_timer")
    if report.dois is not None and hasattr(instance, "dois"):
        instance.dois = list(report.dois)
        fields.append("dois")

    if terminal:
        instance.task_end_time = report.end_time or now
        fields.append("task_end_time")

    fields += [f for f in extra_fields if f not in fields]

    if claim and report.state == instance.STARTED:
        # Exactly one caller wins: the row must still be waiting. STARTED is
        # excluded on purpose - a row that is already running belongs to
        # another worker.
        model = type(instance)
        waiting = model.objects.filter(pk=instance.pk).exclude(
            task_state__in=(*_terminal_states(instance), instance.STARTED)
        )
        updated = waiting.update(**{f: getattr(instance, f) for f in fields})
        if not updated:
            _log.info(
                "%s %s: lost the claim, another worker is running or has finished "
                "this row.",
                model.__name__,
                instance.pk,
            )
            instance.refresh_from_db(fields=fields)
            return False
    else:
        instance.save(update_fields=fields)

    if terminal and report.state == instance.SUCCESS and report.files:
        folder = getattr(instance, "folder", None)
        if folder is not None:
            folder.register_files(report.files)
        else:
            _log.warning(
                "%s %s reported %d files but has no folder to record them in.",
                type(instance).__name__,
                instance.pk,
                len(report.files),
            )

    _fire_lifecycle_hooks(instance, report)
    return True


def _fire_lifecycle_hooks(instance, report: StatusReport):
    """
    Call every hook in ``TOPOBANK_TASK_LIFECYCLE_HOOKS`` with ``(instance, report)``.

    Hooks are import strings. A failing hook is logged and never breaks the
    report: status must reach the database even if a notification channel is
    down.
    """
    for path in getattr(settings, "TOPOBANK_TASK_LIFECYCLE_HOOKS", ()) or ():
        try:
            import_string(path)(instance, report)
        except Exception:  # noqa: BLE001 - deliberately broad, see docstring
            _log.exception(
                "Lifecycle hook %s failed for %s %s", path, type(instance).__name__, instance.pk
            )
