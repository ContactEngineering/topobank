import inspect
import logging
import traceback

import django.db.models as models
from django.core.cache import cache
from django.utils import timezone
from muTimer import Timer
from SurfaceTopography.Exceptions import CannotDetectFileFormat

from .celeryapp import app
from .memory import track_memory_usage
from .tasks import ProgressRecorder

_log = logging.getLogger(__name__)


def _cache_set(key, value, timeout=30):
    """
    Remember a result-backend value; never let the cache break a status read.

    Values coming back from Celery are not guaranteed to be picklable (an
    exception carrying an odd payload, for instance). Status must still be
    reported then, just without the cache.
    """
    try:
        cache.set(key, value, timeout)
    except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
        _log.debug("Not caching %s: %s", key, exc)


class IncompleteMetadataError(Exception):
    """
    Raised when a data file is of a supported format and can be read, but does
    not contain the complete metadata (physical size, unit) required to process
    it, and the instance is configured (via `TOPOBANK_REJECT_INCOMPLETE_METADATA`)
    to reject such files instead of prompting the user to fill in the metadata.
    """

    pass


class TaskStateModel(models.Model):
    class Meta:
        abstract = True

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

    # Fields mutated by set_pending_state(). Callers that persist with a
    # restricted update_fields must include these, otherwise the pending
    # transition is silently dropped.
    PENDING_STATE_FIELDS = (
        "task_state",
        "task_submission_time",
        "task_error",
        "task_traceback",
        "task_id",
        "task_start_time",
        "task_end_time",
        "execution_handle",
    )

    # Where the run lives: a serialised `topobank.taskapp.launch.LaunchHandle`
    # naming the workflow manager that launched this row and whatever that
    # manager needs to find the run again. None until launched. This is the only
    # execution reference the launch API knows about; the two Celery ids below
    # are the Celery manager's own bookkeeping.
    execution_handle = models.JSONField(null=True)

    # Celery manager bookkeeping: the id of the Celery task currently
    # responsible for this row. Set by the Celery manager on dispatch and
    # overwritten by the task once it runs.
    task_id = models.UUIDField(unique=True, null=True)

    # Celery manager bookkeeping: the id of the Celery task that launched a
    # chord of dependencies for this row, if there were any.
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

    # --- Launch API -------------------------------------------------------
    #
    # Everything below asks the workflow manager that launched this row. The
    # manager is found through `execution_handle`; rows launched before handles
    # existed fall back to the default manager.

    def build_launch_request(self, *, force=False, **fields):
        """
        Describe the work this row represents as a `LaunchRequest`.

        The default is a plain task: the manager calls `task_worker` with the
        given `args` and `task_kwargs`. Subclasses that represent workflows
        override this to fill in the workflow envelope.
        """
        from .launch import LaunchRequest

        request = dict(
            kind="task",
            model=f"{self._meta.app_label}.{self._meta.model_name}",
            pk=self.pk,
            force=force,
            queue=self.get_queue(),
        )
        request.update(fields)
        return LaunchRequest(**request)

    def get_queue(self):
        """
        Logical queue this row's work should run on, or None for the default.

        A logical name (e.g. "manager") is a resource hint for the workflow
        manager; how it maps onto a real queue is the manager's business.
        """
        return getattr(self, "celery_queue", None)

    def get_launch_handle(self):
        """The handle of this row's run, or a handle for the default manager."""
        from .launch import LaunchHandle, get_default_manager_name

        if self.execution_handle:
            return LaunchHandle(**self.execution_handle)
        return LaunchHandle(
            manager=get_default_manager_name(),
            data={
                "model": f"{self._meta.app_label}.{self._meta.model_name}",
                "pk": self.pk,
            },
        )

    def get_workflow_manager(self):
        """The workflow manager responsible for this row's run."""
        from .launch import get_workflow_manager

        return get_workflow_manager(self.get_launch_handle().manager)

    def poll(self):
        """Ask the workflow manager what it knows about this row's run."""
        if hasattr(self, "_cached_run_info"):
            return self._cached_run_info
        info = self.get_workflow_manager().poll(self.get_launch_handle(), instance=self)
        self._cached_run_info = info
        return info

    # --- Celery manager bookkeeping ----------------------------------------
    #
    # These helpers read Celery's result backend for this row and are used by
    # the Celery workflow manager. They are kept on the model because the
    # manager's state *is* the row (task_id, launcher_task_id).

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
        _cache_set(cache_key, state)

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
        _cache_set(cache_key, info)

        return info

    # --- Reconciled task state --------------------------------------------

    def get_manager_state(self):
        """Return the state of the task as reported by the workflow manager"""
        # Optimization: If task is in terminal state, return DB value without
        # asking the manager
        if self.task_state in (TaskStateModel.SUCCESS, TaskStateModel.FAILURE):
            return self.task_state
        return self.poll().state

    # Kept under its historical name; the state no longer necessarily comes
    # from Celery.
    get_celery_state = get_manager_state

    def get_task_state(self):
        """
        Return the most likely state of the task from the self-reported task
        information in the database and the information obtained from the
        workflow manager.
        """
        # This is self-reported by the task runner
        self_reported_task_state = self.task_state
        if self_reported_task_state in (TaskStateModel.SUCCESS, TaskStateModel.FAILURE):
            # If the task self-reports success or failure, we trust it without further checks
            return self_reported_task_state

        # Self-reported state is not SUCCESS or FAILURE, check with the manager
        manager_task_state = self.get_celery_state()

        if self_reported_task_state == manager_task_state:
            # We're good!
            return self_reported_task_state
        else:
            if manager_task_state == TaskStateModel.FAILURE:
                # The manager seems to think this task failed, we trust it as the
                # self-reported state will be unreliable in this case.
                _log.error(
                    f"The {self.__class__.__name__} instance with id {self.id} self-reported "
                    f"the state '{self_reported_task_state}', but the workflow manager "
                    f"reported '{manager_task_state}'. I am returning a failure."
                )
                return TaskStateModel.FAILURE
            elif (
                self_reported_task_state == TaskStateModel.PENDING
                and manager_task_state == TaskStateModel.NOTRUN
            ):
                if not self.task_submission_time:
                    return TaskStateModel.FAILURE

                # The task is marked as pending but the manager thinks the task was
                # never run. This corresponds to the initial creation of the task.
                # The task is launched in an `on_commit` hook. If the task is older
                # than a threshold, we assume the on-commit never triggered and report
                # and error.
                if timezone.now() - self.task_submission_time > timezone.timedelta(
                    seconds=self.COMMIT_EXPIRATION
                ):
                    _log.error(
                        f"The {self.__class__.__name__} instance with id {self.id} "
                        f"self-reported the state '{self_reported_task_state}', but "
                        f"the workflow manager reported '{manager_task_state}'. The "
                        f"database object was created more than {self.COMMIT_EXPIRATION} "
                        "seconds ago. I am returning a failure."
                    )
                    return TaskStateModel.FAILURE
                else:
                    _log.debug(
                        f"The {self.__class__.__name__} instance with id {self.id} "
                        f"self-reported the state '{self_reported_task_state}', but "
                        f"the workflow manager reported '{manager_task_state}'. The "
                        f"database object was created less than {self.COMMIT_EXPIRATION} "
                        "seconds ago. I am returning a pending state."
                    )
                    return TaskStateModel.PENDING
            else:
                # In all other cases, we trust the self-reported state.
                _log.debug(
                    f"The {self.__class__.__name__} instance with id {self.id} self-reported "
                    f"the state '{self_reported_task_state}', but the workflow manager "
                    f"reported '{manager_task_state}'. I am returning the self-reported state."
                )
                return self_reported_task_state

    def get_task_progress(self):
        """Return progress of task, if running"""
        # Optimization: If task is in terminal state, return appropriate value
        # without asking the manager
        if self.task_state == TaskStateModel.SUCCESS:
            return 100.0
        elif self.task_state == TaskStateModel.FAILURE:
            return None
        return self.poll().progress

    def get_task_messages(self):
        """Return progress message(s) of the task, if running"""
        # Optimization: If task is in terminal state, return empty list without
        # asking the manager
        if self.task_state in (TaskStateModel.SUCCESS, TaskStateModel.FAILURE):
            return []
        return self.poll().messages

    def set_pending_state(self, autosave=True):
        self.task_state = self.PENDING
        self.task_submission_time = timezone.now()
        self.task_error = ""
        self.task_traceback = None
        self.task_id = None  # Need to reset, otherwise Celery reports a failure
        self.execution_handle = None  # A new launch produces a new handle
        # Clear timestamps from any prior run so a re-pended row looks freshly
        # created: otherwise duration() reports garbage and a stale task_start_time
        # could be mistaken for an in-flight run.
        self.task_start_time = None
        self.task_end_time = None
        if autosave:
            self.save(update_fields=list(self.PENDING_STATE_FIELDS))

    def get_task_error(self):
        """Return a string representation of any error occurred during task execution"""
        # Return self-reported task error, if any
        if self.task_error:
            return self.task_error

        # If there is none, ask the manager
        error = self.poll().error
        if error:
            # There seems to be an error, store for future reference
            from .status import StatusReport, apply_status_report

            apply_status_report(self, StatusReport(state=self.FAILURE, error=error))
            return self.task_error
        return None

    def cancel_task(self):
        """Cancel task, if running"""
        self.get_workflow_manager().cancel(self.get_launch_handle(), instance=self)

    def task_worker(self, *args, **kwargs):
        """The actual task"""
        raise NotImplementedError

    def run_task(self, celery_task, *args, **kwargs):
        """
        Execute the task worker and store states to database.

        Parameters
        ----------
        celery_task : celery.Task
            The Celery task to be executed.
        *args : tuple
            Additional positional arguments for the task.
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
        self.task_state = TaskStateModel.STARTED
        self.task_id = celery_task.request.id
        self.task_start_time = timezone.now()  # with timezone
        self.save()  # save such that any queries see this as running

        # actually run the task
        try:
            # Peak-memory tracking: cheap RSS high-water mark by default;
            # precise (but ~35x slower on numeric workloads) tracemalloc only
            # when TOPOBANK_TRACK_MEMORY_USAGE is enabled. See taskapp/memory.py.
            with track_memory_usage() as memory_usage:
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
            self.task_state = TaskStateModel.SUCCESS
            self.task_memory = memory_usage.peak
            self.task_error = ""
        except CannotDetectFileFormat:
            self.task_state = TaskStateModel.FAILURE
            self.task_error = "The data file is of an unknown or unsupported format."
            self.task_traceback = traceback.format_exc().replace('\x00', '')
        except IncompleteMetadataError as exc:
            # The file is of a supported format but lacks required metadata, and
            # this instance is configured to reject such files. This is an expected
            # user-input rejection (not a system fault), so we do not re-raise.
            self.task_state = TaskStateModel.FAILURE
            self.task_error = str(exc).replace('\x00', '')
            self.task_traceback = traceback.format_exc().replace('\x00', '')
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
            self.save()


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
