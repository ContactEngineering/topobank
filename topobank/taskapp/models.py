import inspect
import logging
import traceback
from datetime import datetime
from decimal import Decimal
from typing import NamedTuple, Optional

import celery.states
import django.db.models as models
import pydantic
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from muTimer import Timer
from SurfaceTopography.Exceptions import CannotDetectFileFormat

from .celeryapp import app
from ..exceptions import IncompleteMetadataError  # noqa: F401 - imported from here
from ..exceptions import TaskBackendError
from .memory import track_memory_usage
from .tasks import ProgressRecorder

_log = logging.getLogger(__name__)


class TaskRun(NamedTuple):
    """A run of a task model's task, identified by its task id and start time."""

    task_id: str
    start_time: Optional[datetime]
    # Ended through `complete_task`: the run is over once the row is no longer
    # `STARTED`, whatever ended it
    while_started: bool = False


class TaskStateModel(models.Model):
    class Meta:
        abstract = True
        # Django takes the first manager declared as a model's default, and the
        # managers declared here count as declared before any of a subclass's:
        # without this, a subclass's default manager would silently become one
        # of these. A subclass with a `Meta` of its own keeps it only by
        # extending this one (`class Meta(TaskStateModel.Meta)`).
        default_manager_name = "objects"

    # `all_objects` holds every row, also those a subclass's `objects` hides (the
    # soft-deleted ones, say). The task machinery goes through it: a run of a row
    # deleted meanwhile still ends, is reaped, and is cleaned up after. A
    # subclass may redefine either manager, as long as `all_objects` stays
    # unfiltered.
    objects = models.Manager()
    all_objects = models.Manager()

    # Time to wait for a task to be submitted after creation/update of the database
    # entry.
    COMMIT_EXPIRATION = 30  # seconds

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

    # States indicating a task is dispatched or running. RETRY is deliberately
    # excluded: a task awaiting retry is not currently running and keeps its
    # original (now-stale) task_start_time.
    IN_FLIGHT_STATES = (PENDING, PENDING_DEPENDENCIES, STARTED)

    # Fields `pending_state_values` sets when a task is submitted. `run_task`
    # (see `taskapp.utils`) writes them to the database itself; a caller only
    # needs to save them after `set_pending_state(autosave=False)`.
    PENDING_STATE_FIELDS = (
        "task_state",
        "task_submission_time",
        "task_error",
        "task_traceback",
        "task_id",
        "task_start_time",
        "task_end_time",
    )

    # Fields `run_task` writes when a run ends.
    TASK_RESULT_FIELDS = (
        "task_state",
        "task_end_time",
        "task_error",
        "task_traceback",
        "task_memory",
        "task_timer",
    )

    # Every field the task machinery owns
    TASK_FIELDS = PENDING_STATE_FIELDS + ("task_memory", "task_timer", "launcher_task_id")

    # The run in progress on this instance (a `TaskRun`), or None. Set by
    # `run_task` and `complete_task` for the duration of the run;
    # `is_current_task_run` compares it with the row to tell whether a newer
    # dispatch took over.
    _task_run = None

    # Mapping Celery states to our state information. Everything not in the
    # list (e.g. custom Celery states) are interpreted as STARTED.
    _CELERY_STATE_MAP = {
        celery.states.SUCCESS: SUCCESS,
        celery.states.STARTED: STARTED,
        celery.states.PENDING: PENDING,
        celery.states.RECEIVED: PENDING,
        celery.states.RETRY: PENDING,
        # The following are in celery.states.EXCEPTION_STATES
        celery.states.FAILURE: FAILURE,
        celery.states.REVOKED: FAILURE,
        celery.states.REJECTED: FAILURE,
    }

    # This is the Celery task id
    task_id = models.UUIDField(unique=True, null=True)
    # Django documentation discourages the use of null=True on a CharField. I'll use it
    # here  nevertheless, because I need this values as argument to a function where
    # None has a special meaning (task not yet run).

    # This is the Celery id of the task that launched the chord (if there are
    # dependencies)
    launcher_task_id = models.UUIDField(unique=True, null=True)

    # This is the self-reported task state. It can differ from what Celery
    # knows about the task.
    task_state = models.CharField(
        max_length=2, choices=TASK_STATE_CHOICES, default=NOTRUN
    )

    # Maximum memory usage of the task
    task_memory = models.BigIntegerField(null=True)

    # Any error information emitted from the task
    task_error = models.TextField(default="")
    task_traceback = models.TextField(null=True)

    # Time stamps
    task_submission_time = models.DateTimeField(null=True)
    task_start_time = models.DateTimeField(null=True)
    task_end_time = models.DateTimeField(null=True)
    task_timer = models.JSONField(null=True)

    @property
    def task_duration(self):
        """
        Returns duration of computation or None if not finished yet.

        Does not take into account the queue time.

        Returns
        -------
        datetime.timedelta or None
            Returns the duration of the computation or None if not finished yet.
        """
        if self.task_end_time is None or self.task_start_time is None:
            return None

        return self.task_end_time - self.task_start_time

    def get_async_result(self):
        """Return the Celery result object"""
        if self.task_id is None:
            return None
        return app.AsyncResult(str(self.task_id))

    def get_async_results(self):
        """Return the Celery result objects of current and dependent tasks"""
        # Check if results are cached (for performance during serialization)
        if hasattr(self, '_cached_async_results'):
            return self._cached_async_results

        task_result = self.get_async_result()
        launcher_task_result = (
            app.AsyncResult(str(self.launcher_task_id))
            if self.launcher_task_id
            else None
        )

        # Get task results of all children (if this was run as a chord)
        task_results = []
        if (
            launcher_task_result
            and launcher_task_result.children
            and len(launcher_task_result.children) > 0
        ):
            task_results = (
                [*[r for r in launcher_task_result.children[0].children]]
                if launcher_task_result
                else []
            )
        if task_result:
            task_results += [task_result]

        # Cache the results on the instance to avoid repeated Celery queries
        self._cached_async_results = task_results

        return task_results

    def _get_result_state(self, async_result):
        """
        Get state from AsyncResult with Redis caching to avoid repeated Celery queries.

        Args:
            async_result: Celery AsyncResult object

        Returns:
            str: Task state from Celery
        """
        if async_result is None:
            return None

        task_id = str(async_result.id)
        cache_key = f'celery_state:{task_id}'

        # Try to get from cache
        cached_state = cache.get(cache_key)
        if cached_state is not None:
            return cached_state

        # Query Celery and cache for 30 seconds
        state = async_result.state
        cache.set(cache_key, state, 30)

        return state

    def _get_result_info(self, async_result):
        """
        Get info from AsyncResult with Redis caching to avoid repeated Celery queries.

        Args:
            async_result: Celery AsyncResult object

        Returns:
            Task info/result from Celery
        """
        if async_result is None:
            return None

        task_id = str(async_result.id)
        cache_key = f'celery_info:{task_id}'

        # Try to get from cache
        cached_info = cache.get(cache_key)
        if cached_info is not None:
            return cached_info

        # Query Celery and cache for 30 seconds
        info = async_result.info
        cache.set(cache_key, info, 30)

        return info

    def get_celery_state(self):
        """Return the state of the task as reported by Celery"""
        # Optimization: If task is in terminal state, return DB value without querying Celery
        if self.task_state in (TaskStateModel.SUCCESS, TaskStateModel.FAILURE):
            return self.task_state

        # Check if any of the dependent tasks failed
        for r in self.get_async_results():
            state = self._get_result_state(r)
            if state in celery.states.EXCEPTION_STATES:
                return TaskStateModel.FAILURE

        # Check state of current task
        if self.task_id is None:
            # Cannot get the state
            return TaskStateModel.NOTRUN
        else:
            r = self.get_async_result()
            state = self._get_result_state(r)
            try:
                state = self._CELERY_STATE_MAP[state]
            except KeyError:
                # Everything else (e.g. a custom state such as 'PROGRESS') is interpreted
                # as a running task
                state = TaskStateModel.STARTED
            return state

    def get_task_state(self):
        """
        Return the most likely state of the task from the self-reported task
        information in the database and the information obtained from Celery.
        """
        # This is self-reported by the task runner
        self_reported_task_state = self.task_state
        if self_reported_task_state in (TaskStateModel.SUCCESS, TaskStateModel.FAILURE):
            # If the task self-reports success or failure, we trust it without further checks
            return self_reported_task_state

        # Self-reported state is not SUCCESS or FAILURE, check with Celery
        # This is what Celery reports back
        celery_task_state = self.get_celery_state()

        if self_reported_task_state == celery_task_state:
            # We're good!
            return self_reported_task_state
        else:
            if celery_task_state == TaskStateModel.FAILURE:
                # Celery seems to think this task failed, we trust it as the
                # self-reported state will be unreliable in this case.
                _log.error(
                    f"The {self.__class__.__name__} instance with id {self.id} self-reported "
                    f"the state '{self_reported_task_state}', but Celery reported "
                    f"'{celery_task_state}'. I am returning a failure."
                )
                return TaskStateModel.FAILURE
            elif (
                self_reported_task_state == TaskStateModel.PENDING
                and celery_task_state == TaskStateModel.NOTRUN
            ):
                if not self.task_submission_time:
                    return TaskStateModel.FAILURE

                # The task is marked as pending but Celery thinks the task was never
                # run. This corresponds to the initial creation of the task. The
                # Celery task is started in an `on_commit` hook. If the task is older
                # than a threshold, we assume the on-commit never triggered and report
                # and error.
                if timezone.now() - self.task_submission_time > timezone.timedelta(
                    seconds=self.COMMIT_EXPIRATION
                ):
                    _log.error(
                        f"The {self.__class__.__name__} instance with id {self.id} "
                        f"self-reported the state '{self_reported_task_state}', but "
                        f"Celery reported '{celery_task_state}'. The database object "
                        f"was created more than {self.COMMIT_EXPIRATION} seconds ago. "
                        "I am returning a failure."
                    )
                    return TaskStateModel.FAILURE
                else:
                    _log.debug(
                        f"The {self.__class__.__name__} instance with id {self.id} "
                        f"self-reported the state '{self_reported_task_state}', but "
                        f"Celery reported '{celery_task_state}'. The database object "
                        f"was created less than {self.COMMIT_EXPIRATION} seconds ago. "
                        "I am returning a pending state."
                    )
                    return TaskStateModel.PENDING
            else:
                # In all other cases, we trust the self-reported state.
                _log.debug(
                    f"The {self.__class__.__name__} instance with id {self.id} self-reported "
                    f"the state '{self_reported_task_state}', but Celery reported "
                    f"'{celery_task_state}'. I am returning the self-reported state."
                )
                return self_reported_task_state

    def get_task_progress(self):
        """Return progress of task, if running"""
        # Optimization: If task is in terminal state, return appropriate value without querying Celery
        if self.task_state == TaskStateModel.SUCCESS:
            return 100.0
        elif self.task_state == TaskStateModel.FAILURE:
            return None

        # Get all tasks
        task_results = self.get_async_results()

        # Sum up progress of all children
        total = 0
        current = 0
        for r in task_results:
            # Use cached state and info to avoid repeated Celery queries
            state = self._get_result_state(r)
            info = self._get_result_info(r)

            # First check for errors
            if state in celery.states.EXCEPTION_STATES or isinstance(info, Exception):
                # Some of the tasks failed, we return no progress
                return None
            elif state == celery.states.SUCCESS:
                total += 1
                current += 1
            elif state == celery.states.PENDING:
                total += 1
            elif info:
                # We assume that the state is 'PROGRESS' and we can just extract the
                # progress dictionary.
                try:
                    task_progress = ProgressRecorder.Model(**info)
                except pydantic.ValidationError:
                    _log.info(
                        f"Validation of progress dictionary for task {r} of analysis "
                        f"{self} failed. Ignoring task progress."
                    )
                    pass
                except TypeError:
                    _log.info(
                        f"Progress dictionary for task {r} of analysis {self} failed "
                        "does not appear to be a dictionary. Ignoring task progress."
                    )
                    pass
                else:
                    total += 1
                    current += task_progress.current / task_progress.total

        # Compute percentage
        percent = 0
        if total > 0:
            percent = (Decimal(current) / Decimal(total)) * Decimal(100)
            percent = float(round(percent, 2))

        return percent

    def get_task_messages(self):
        """Return progress message(s) of the task, if running"""
        # Optimization: If task is in terminal state, return empty list without querying Celery
        if self.task_state in (TaskStateModel.SUCCESS, TaskStateModel.FAILURE):
            return []

        # Get all tasks
        task_results = self.get_async_results()

        messages = []
        for r in task_results:
            # Use cached state and info to avoid repeated Celery queries
            state = self._get_result_state(r)
            info = self._get_result_info(r)

            # First check for errors
            if state in celery.states.EXCEPTION_STATES or isinstance(info, Exception):
                # Some of the tasks failed, we return no progress message
                return None
            elif state == celery.states.SUCCESS or state == celery.states.PENDING:
                # Task finished or is pending, no progress message
                pass
            elif info:
                # We assume that the state is 'PROGRESS' and we can just extract the
                # progress dictionary.
                try:
                    task_progress = ProgressRecorder.Model(**info)
                except pydantic.ValidationError:
                    _log.info(
                        f"Validation of progress dictionary for task {r} of analysis "
                        f"{self} failed. Ignoring task progress."
                    )
                    pass
                except TypeError:
                    _log.info(
                        f"Progress dictionary for task {r} of analysis {self} failed "
                        "does not appear to be a dictionary. Ignoring task progress."
                    )
                    pass
                else:
                    messages += [task_progress.message]

        return messages

    @classmethod
    def pending_state_values(cls, task_id=None):
        """Values of `PENDING_STATE_FIELDS` for a freshly submitted task."""
        return {
            "task_state": cls.PENDING,
            "task_submission_time": timezone.now(),
            "task_error": "",
            "task_traceback": None,
            # Need to reset, otherwise Celery reports a failure
            "task_id": task_id,
            # Clear timestamps from any prior run so a re-pended row looks freshly
            # created: otherwise duration() reports garbage and a stale
            # task_start_time could be mistaken for an in-flight run.
            "task_start_time": None,
            "task_end_time": None,
        }

    def set_pending_state(self, autosave=True):
        for name, value in self.pending_state_values().items():
            setattr(self, name, value)
        if autosave:
            self.save(update_fields=list(self.PENDING_STATE_FIELDS))

    def get_task_error(self):
        """Return a string representation of any error occurred during task execution"""
        # Return self-reported task error, if any
        if self.task_error:
            return self.task_error

        # If there is none, check Celery
        for r in self.get_async_results():
            # Use cached info to avoid repeated Celery queries
            info = self._get_result_info(r)
            # We simply fail with the first error we encounter
            if r and isinstance(info, Exception):
                # Generate error string
                self.task_state = self.FAILURE
                self.task_error = str(info).replace('\x00', '')
                # There seems to be an error, store for future reference
                self.save(update_fields=["task_state", "task_error"])
                return self.task_error
        return None

    def cancel_task(self):
        """Cancel task, if running"""
        r = self.get_async_result()
        if r:
            r.revoke()

    def task_worker(self, *args, **kwargs):
        """The actual task"""
        raise NotImplementedError

    def run_task(self, celery_task, *args, claimed_run=None, **kwargs):
        """
        Execute the task worker and store states to database.

        Parameters
        ----------
        celery_task : celery.Task
            The Celery task to be executed.
        *args : tuple
            Additional positional arguments for the task.
        claimed_run : tuple, optional
            The run (task id, start time) that `task_dispatch` claimed for this
            delivery before loading the instance. None when the task runs inline,
            in which case this method marks the row as started itself.
        **kwargs : dict
            Additional keyword arguments for the task.

        Raises
        ------
        CannotDetectFileFormat
            If the data file is of an unknown or unsupported format.
        IncompleteMetadataError
            If the data file is of a supported format but lacks required metadata
            and this instance is configured to reject such files. Caught and stored
            as a task error; not propagated.
        Exception
            For any other exceptions that occur during task execution.
        """
        task_id = celery_task.request.id
        if claimed_run is not None:
            # Claimed by `task_dispatch` before this instance was loaded. The row
            # may have been claimed again since, by a newer dispatch; that run
            # supersedes this one, which then leaves the row alone.
            if (str(self.task_id), self.task_start_time) != claimed_run:
                _log.info(
                    "%s id=%s: run %s was superseded by a newer dispatch before it "
                    "started; not running it.",
                    type(self).__name__,
                    self.pk,
                    task_id,
                )
                return False
        else:
            # A caller runs the task inline
            self.task_state = TaskStateModel.STARTED
            self.task_id = task_id
            self.task_start_time = timezone.now()  # with timezone
            # save such that any queries see this as running
            self.save(update_fields=["task_state", "task_id", "task_start_time"])
        # The task id and start time identify this run. A forced re-dispatch or a
        # takeover by a redelivered message replaces them, and this run then
        # leaves the row to its successor.
        outer_run = self._task_run
        self._task_run = TaskRun(str(self.task_id), self.task_start_time)

        def work():
            # Pass the optional `timer` and `progress_recorder` arguments only
            # to workers that declare them, so that a worker can opt into
            # timing and progress reporting without every worker having to
            # accept both.
            sig = inspect.signature(self.task_worker)
            extra_kwargs = {}
            timer = None
            if 'timer' in sig.parameters:
                timer = Timer(str(self.task_id))
                extra_kwargs['timer'] = timer
            if 'progress_recorder' in sig.parameters:
                extra_kwargs['progress_recorder'] = ProgressRecorder(celery_task)
            self.task_worker(*args, **extra_kwargs, **kwargs)
            if timer is not None:
                self.task_timer = timer.to_dict()

        try:
            self._record_run(work)
        finally:
            self._task_run = outer_run

    def complete_task(self, task_id, work):
        """End the run `task_id` that a task backend carried out elsewhere.

        A backend (see `task_backend`) runs the task outside the Celery worker, and
        hands what it produced back here: `work` records it, as `task_worker` would
        have, and the run then ends as `run_task` ends it -- a success, or a
        failure with the error `work` raises. A backend reports a failure of its
        own by having `work` raise `TaskBackendError`. Nothing happens unless the
        row is still in that run, i.e. started under `task_id` and not superseded
        by a newer dispatch since. Unlike a Celery run, which owns its result even
        once the custodian has given it up for lost, the run is no longer this
        one's once it has been ended otherwise (failed as lost, say): the
        custodian then cleans up after it.

        Returns whether the end of the run was recorded here.
        """
        self.refresh_from_db(fields=list(self.PENDING_STATE_FIELDS))
        if str(self.task_id) != str(task_id) or self.task_state != self.STARTED:
            _log.info(
                "%s id=%s: run %s is not in progress (state=%s, task %s); not "
                "recording its result.",
                type(self).__name__,
                self.pk,
                task_id,
                self.task_state,
                self.task_id,
            )
            return False
        outer_run = self._task_run
        self._task_run = TaskRun(
            str(self.task_id), self.task_start_time, while_started=True
        )
        # What the backend used is unknown here; the values of an earlier run are
        # not this run's
        self.task_memory = None
        self.task_timer = None
        try:
            return self._record_run(work, track_memory=False)
        finally:
            self._task_run = outer_run

    def _record_run(self, work, track_memory=True):
        """Call `work` as the run `_task_run` and record how the run ended.

        Returns whether that was recorded (see `_save_task_result`).
        """
        try:
            # Peak-memory tracking: cheap RSS high-water mark by default;
            # precise (but ~35x slower on numeric workloads) tracemalloc only
            # when TOPOBANK_TRACK_MEMORY_USAGE is enabled. See taskapp/memory.py.
            if track_memory:
                with track_memory_usage() as memory_usage:
                    work()
                self.task_memory = memory_usage.peak
            else:
                work()
            self.task_state = TaskStateModel.SUCCESS
            self.task_error = ""
        except CannotDetectFileFormat:
            self.task_state = TaskStateModel.FAILURE
            self.task_error = "The data file is of an unknown or unsupported format."
            self.task_traceback = traceback.format_exc().replace('\x00', '')
        except (IncompleteMetadataError, TaskBackendError) as exc:
            # The file is of a supported format but lacks required metadata, and
            # this instance is configured to reject such files; or a backend
            # reports that its run failed. Either is the outcome of the run (not
            # a fault here), so we do not re-raise.
            self.task_state = TaskStateModel.FAILURE
            self.task_error = str(exc).replace('\x00', '')
            self.task_traceback = (
                getattr(exc, "traceback", None) or traceback.format_exc()
            ).replace('\x00', '')
        except Exception as exc:
            self.task_state = TaskStateModel.FAILURE
            # Store string representation of exception and traceback as user-reported
            # error string
            self.task_error = str(exc).replace('\x00', '')
            self.task_traceback = traceback.format_exc().replace('\x00', '')
            # we want a real exception here so celery's flower can show the task as
            # failure
            raise
        finally:
            # Store time stamp and save state to database
            self.task_end_time = timezone.now()  # with timezone
            recorded = self._save_task_result()
        return recorded

    def task_backend(self):
        """A callable ``backend(instance, task_id)`` that runs this instance's
        claimed task instead of the Celery task, or None (the default) for the
        Celery task.

        The run is started (``STARTED``) when it is handed to the backend, which
        ends it through ``complete_task`` (see ``taskapp.utils.submit_on_commit``).
        Until then it counts as lost like a Celery run that no worker holds: the
        custodian fails it once it is older than its minimum age.
        """
        return None

    def task_lost(self):
        """Called once the custodian has failed this instance's run as lost, to
        clean up after it. Does nothing by default.

        It runs in the custodian after the row has been moved to ``FAILURE``,
        outside any transaction: an implementation may touch storage, but cannot
        roll the row back.
        """

    def task_save_fields(self):
        """Fields to persist when a run ends, or None to save the whole row.

        Override this when the task worker persists its own results, so that the
        end of a run does not overwrite fields changed elsewhere in the meantime.
        """
        return None

    def _lock_row(self, *fields):
        """Lock this row until the end of the surrounding transaction.

        Returns the row's run token (task id and start time), its task state and
        the values of `fields`, or None if the row is gone.
        """
        return (
            type(self)
            .all_objects.select_for_update()
            .filter(pk=self.pk)
            .values("task_id", "task_start_time", "task_state", *fields)
            .first()
        )

    def is_current_task_run(self, row=None) -> bool:
        """Whether the row still belongs to the run in progress, if any.

        Locks the row until the end of the surrounding transaction, unless the
        caller passes the `row` it has locked already. Outside a run (no run in
        progress) this is always True.
        """
        run = self._task_run
        if run is None:
            return True
        if row is None:
            row = self._lock_row()
        if row is None or (str(row["task_id"]), row["task_start_time"]) != (
            run.task_id,
            run.start_time,
        ):
            return False
        return not run.while_started or row["task_state"] == self.STARTED

    def _save_task_result(self):
        """Record how the run ended; returns whether it still was this run's."""
        with transaction.atomic():
            if not self.is_current_task_run():
                _log.warning(
                    "%s id=%s: run %s was superseded by a newer dispatch; not "
                    "recording its result (state=%s).",
                    type(self).__name__,
                    self.pk,
                    self.task_id,
                    self.task_state,
                )
                return False
            fields = self.task_save_fields()
            if fields is None:
                self.save()
            else:
                # The run owns its result: written even where another writer (a
                # reaper that gave the run up for lost, say) changed it meanwhile
                self.save(update_fields=list(fields))
        return True


class Dependency(models.Model):
    """A dependency of analysis results, e.g. "SurfaceTopography", "topobank" """

    # this is used with "import":
    import_name = models.CharField(max_length=30, unique=True)

    def __str__(self):
        return self.import_name


class Version(models.Model):
    """
    A specific version of a dependency.
    Part of a configuration.
    """

    class Meta:
        constraints = [
            # `micro` and `extra` are nullable and are NULL for most releases
            # (a clean "1.70.0" parses to extra=None). A plain `unique_together`
            # maps to a UNIQUE constraint, and PostgreSQL treats NULLs as
            # distinct there, so it did *not* prevent duplicate rows for exactly
            # the common case. Two workers calling `get_or_create()` for a
            # freshly deployed version could therefore both insert, and every
            # later `get_or_create()` would raise `MultipleObjectsReturned`,
            # failing every analysis. `nulls_distinct=False` (PostgreSQL 15+)
            # makes NULL compare equal so the constraint actually holds.
            models.UniqueConstraint(
                fields=["dependency", "major", "minor", "micro", "extra"],
                name="unique_version_per_dependency",
                nulls_distinct=False,
            )
        ]

    dependency = models.ForeignKey(Dependency, on_delete=models.CASCADE)

    major = models.SmallIntegerField()
    minor = models.SmallIntegerField()
    micro = models.SmallIntegerField(null=True)
    extra = models.CharField(max_length=100, null=True)

    # the following can be used to indicate that this
    # version should not be used any more / or the analyses
    # should be recalculated
    # valid = models.BooleanField(default=True)

    def number_as_string(self):
        if self.major == 0 and self.minor == 0 and self.micro is None and self.extra is not None:
            return self.extra
        x = f"{self.major}.{self.minor}"
        if self.micro is not None:
            x += f".{self.micro}"
        if self.extra is not None:
            x += self.extra
        return x

    def __str__(self):
        return f"{self.dependency} {self.number_as_string()}"


class Configuration(models.Model):
    """For keeping track which versions were used for an analysis."""

    valid_since = models.DateTimeField(auto_now_add=True)
    versions = models.ManyToManyField(Version)

    def __str__(self):
        versions = [str(v) for v in self.versions.all()]
        return f"Valid since: {self.valid_since}, versions: {versions}"
