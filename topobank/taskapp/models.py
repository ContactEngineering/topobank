import logging
import traceback
import tracemalloc
from decimal import Decimal

import celery.states
import django.db.models as models
import pydantic
from django.core.cache import cache
from django.utils import timezone
from muGrid.Timer import Timer
from SurfaceTopography.Exceptions import CannotDetectFileFormat

from .celeryapp import app
from .tasks import ProgressRecorder

_log = logging.getLogger(__name__)


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

    def set_pending_state(self, autosave=True):
        self.task_state = self.PENDING
        self.task_submission_time = timezone.now()
        self.task_error = ""
        self.task_traceback = None
        self.task_id = None  # Need to reset, otherwise Celery reports a failure
        if autosave:
            self.save(
                update_fields=[
                    "task_state",
                    "task_submission_time",
                    "task_error",
                    "task_traceback",
                    "task_id",
                ]
            )

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
        Exception
            For any other exceptions that occur during task execution.
        """
        self.task_state = TaskStateModel.STARTED
        self.task_id = celery_task.request.id
        self.task_start_time = timezone.now()  # with timezone
        self.save()  # save such that any queries see this as running

        # actually run the task
        try:
            tracemalloc.start()
            tracemalloc.reset_peak()
            timer = Timer(str(self.task_id))
            self.task_worker(*args, timer=timer, **kwargs)
            size, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            self.task_state = TaskStateModel.SUCCESS
            self.task_memory = peak
            self.task_error = ""
            self.task_timer = timer.to_dict()
        except CannotDetectFileFormat:
            self.task_state = TaskStateModel.FAILURE
            self.task_error = "The data file is of an unknown or unsupported format."
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
        unique_together = (("dependency", "major", "minor", "micro", "extra"),)

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
