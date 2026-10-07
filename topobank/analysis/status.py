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
says which files it wrote (as :class:`ManifestEntry` items) and topobank turns that
list into `Manifest` rows. topobank never lists a storage prefix to find out
what a run produced; listing object storage is slow and brittle, and the
engine already knows.

A run's files are *provisional* until its success report settles them: files
reserved before launch, written in-process or reported along the way are
recorded but not confirmed, ``SUCCESS`` confirms them, and a run that never
succeeds leaves the provisional rows behind as the truthful record of what
it managed to write. See ``docs/workflow-engine.rst``, "File registration".
"""

import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

import pydantic
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django.utils.module_loading import import_string

_log = logging.getLogger(__name__)


class ManifestEntry(pydantic.BaseModel):
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

    Every field is applied when given and left alone when ``None``, so a report
    can carry as little as a state change or as much as the full outcome of a
    run. A report without a ``state`` changes no state: engines that can watch
    their runs use it to report files as they are written (an *incremental
    report*), which is optional - an engine that cannot simply reports
    everything with its terminal state.
    """

    model_config = pydantic.ConfigDict(extra="forbid")

    #: A :class:`~topobank.taskapp.models.TaskStateModel` state code, or None
    #: for a report that changes no state.
    state: Optional[str] = None

    error: Optional[str] = None
    traceback: Optional[str] = None

    #: Peak memory of the run in bytes.
    memory: Optional[int] = None
    #: Per-stage timings, as produced by ``muTimer.Timer.to_dict()``.
    timer: Optional[Dict[str, Any]] = None
    #: DOIs of the methods the run used.
    dois: Optional[List[str]] = None

    #: Files the run produced. With ``SUCCESS`` this is the complete set: it is
    #: confirmed and reservations it does not mention are dropped; ``None``
    #: with ``SUCCESS`` confirms everything the run recorded before (in-process
    #: writes, incremental reports). With any other state, or no state, the
    #: files are recorded provisionally.
    files: Optional[List[ManifestEntry]] = None

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

    Notes
    -----
    Files are settled here as well (see the module docstring): a ``SUCCESS``
    report confirms the run's files and a success that leaves a declared,
    non-optional output unproduced is recorded as a ``FAILURE`` naming the
    file. Any other report records its files provisionally.
    extra_fields : iterable of str, optional
        Names of fields the caller has set on ``instance`` that should be
        persisted together with the report (e.g. ``"task_id"``).

    Returns
    -------
    bool
        ``True`` if the report was applied, ``False`` if a claim was lost.
    """
    now = timezone.now()
    fields = []
    terminal = report.state in _terminal_states(instance)
    folder = getattr(instance, "folder", None)

    if report.state is not None:
        instance.task_state = report.state
        fields.append("task_state")

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

    # Files. Settled before the state is written, so that a success whose
    # promised output is missing can still be turned into a failure below.
    if folder is None:
        if report.files:
            _log.warning(
                "%s %s reported %d files but has no folder to record them in.",
                type(instance).__name__,
                instance.pk,
                len(report.files),
            )
    elif report.state == instance.SUCCESS:
        if report.files is not None:
            # Record what the engine reports before judging completeness
            folder.register_files(report.files, confirm=False)
        missing = _missing_declared_outputs(instance, folder)
        if missing:
            # A promise broken: the run is a failure and nothing is settled,
            # so what it did write stays provisional, as for any failed run
            message = (
                "The workflow finished without producing its declared output "
                f"file(s): {', '.join(sorted(missing))}."
            )
            _log.error("%s %s: %s", type(instance).__name__, instance.pk, message)
            report = report.model_copy(update={"state": instance.FAILURE, "error": message})
            instance.task_state = instance.FAILURE
            instance.task_error = message
            if "task_error" not in fields:
                fields.append("task_error")
        elif report.files is not None:
            # The report is the complete set: confirm it, drop everything else
            # the run recorded (reservations never filled, unreported writes)
            reported = [entry.filename for entry in report.files]
            folder.get_provisional_files().exclude(filename__in=reported).delete()
            folder.register_files(report.files, confirm=True)
        else:
            # The run recorded its files as it went (in-process writes,
            # incremental reports); success settles them all
            folder.confirm_all()
    elif report.files:
        # Progress or failure: known to exist, not known to be complete
        folder.register_files(report.files, confirm=False)

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
    elif fields:
        instance.save(update_fields=fields)

    _fire_lifecycle_hooks(instance, report)
    return True


def _missing_declared_outputs(instance, folder) -> set:
    """
    Declared, non-optional output files that are not among the folder's
    confirmed files. Empty for rows that declare no outputs.
    """
    declared = getattr(instance, "declared_outputs", None)
    if declared is None:
        return set()
    required = {
        filename
        for filename, output in declared().items()
        if not getattr(output, "optional", False)
    }
    if not required:
        return set()
    # Present means written: confirmed, or provisional with a file behind it.
    # An unfilled reservation is a promise, not a file.
    present = set(
        folder.get_files()
        .exclude(Q(file__isnull=True) | Q(file=""))
        .values_list("filename", flat=True)
    )
    return required - present


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
