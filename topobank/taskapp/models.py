import traceback
import tracemalloc
from decimal import Decimal

import celery.result
import celery.states
import django.db.models as models
import pydantic
from celery.utils.log import get_task_logger
from django.utils import timezone
from SurfaceTopography.Exceptions import CannotDetectFileFormat

from .celeryapp import app
from .tasks import ProgressRecorder

_log = get_task_logger(__name__)


class TaskStateModel(models.Model):
    class Meta:
        abstract = True

    PENDING = "pe"
    STARTED = "st"
    RETRY = "re"
    FAILURE = "fa"
    SUCCESS = "su"
    NOTRUN = "no"

    TASK_STATE_CHOICES = (
        (PENDING, "pending"),
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
    creation_time = models.DateTimeField(null=True)
    start_time = models.DateTimeField(null=True)
    end_time = models.DateTimeField(null=True)

    @property
    def duration(self):
        """
        Returns duration of computation or None if not finished yet.

        Does not take into account the queue time.

        Returns
        -------
        datetime.timedelta or None
            Returns the duration of the computation or None if not finished yet.
        """
        if self.end_time is None or self.start_time is None:
            return None

        return self.end_time - self.start_time

    def get_async_result(self):
        """Return the Celery result object"""
        if self.task_id is None:
            return None
        return app.AsyncResult(str(self.task_id))

    def get_async_results(self):
        """Return the Celery result objects of current and depndent tasks"""
        task_result = self.get_async_result()
        launcher_task_result = (
            app.AsyncResult(str(self.launcher_task_id))
            if self.launcher_task_id
            else None
        )

        # Get task results of all children (if this was run as a chord)
        task_results = (
            [*[r for r in launcher_task_result.children[0].children]]
            if launcher_task_result
            else []
        )
        if task_result:
            task_results += [task_result]

        return task_results

    def get_celery_state(self):
        """Return the state of the task as reported by Celery"""
        if self.task_id is None:
            # Cannot get the state
            return TaskStateModel.NOTRUN
        r = self.get_async_result()
        try:
            return self._CELERY_STATE_MAP[r.state]
        except KeyError:
            # Everything else (e.g. a custom state such as 'PROGRESS') is interpreted
            # as a running task
            return TaskStateModel.STARTED

    def get_task_state(self):
        """
        Return the most likely state of the task from the self-reported task
        information in the database and the information obtained from Celery.
        """
        # This is self-reported by the task runner
        self_reported_task_state = self.task_state
        # This is what Celery reports back
        celery_task_state = self.get_celery_state()

        if celery_task_state is None:
            # There is no Celery state, possibly because the Celery task has not yet
            # been created
            return self_reported_task_state

        if self_reported_task_state == celery_task_state:
            # We're good!
            return self_reported_task_state
        else:
            if self_reported_task_state == TaskStateModel.SUCCESS:
                # Something is wrong, but we return success if the task self-reports
                # success.
                _log.info(
                    f"The object with id {self.id} self-reported the state "
                    f"'{self_reported_task_state}', but Celery reported "
                    f"'{celery_task_state}'. I am returning a success."
                )
                return TaskStateModel.SUCCESS
            elif celery_task_state == TaskStateModel.FAILURE:
                # Celery seems to think this task failed, we trust it as the
                # self-reported state will be unreliable in this case.
                _log.info(
                    f"The object with id {self.id} self-reported the state "
                    f"'{self_reported_task_state}', but Celery reported "
                    f"'{celery_task_state}'. I am returning a failure."
                )
                return TaskStateModel.FAILURE
            else:
                # In all other cases, we trust the self-reported state.
                _log.info(
                    f"The object with id {self.id} self-reported the state "
                    f"'{self_reported_task_state}', but Celery reported "
                    f"'{celery_task_state}'. I am returning the self-reported state."
                )
                return self_reported_task_state

    def get_task_progress(self):
        """Return progress of task, if running"""
        # Get all tasks
        task_results = self.get_async_results()

        # Sum up progress of all children
        total = 0
        current = 0
        for r in task_results:
            # First check for errors
            if r.state in celery.states.EXCEPTION_STATES or isinstance(
                r.info, Exception
            ):
                # Some of the tasks failed, we return no progress
                return None
            elif r.state == celery.states.SUCCESS:
                total += 1
                current += 1
            elif r.state == celery.states.PENDING:
                total += 1
            elif r.info:
                # We assume that the state is 'PROGRESS' and we can just extract the
                # progress dictionary.
                try:
                    task_progress = ProgressRecorder.Model(**r.info)
                except pydantic.ValidationError:
                    _log.info(
                        f"Validation of progress dictionary for task {r} of analysis "
                        f"{self} failed. Ignoring task progress."
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

    def get_task_error(self):
        """Return a string representation of any error occurred during task execution"""
        # Return self-reported task error, if any
        if self.task_error:
            return self.task_error

        # If there is none, check Celery
        for r in self.get_async_results():
            # We simply fail with the first error we encounter
            if r and isinstance(r.info, Exception):
                # Generate error string
                self.task_state = self.FAILURE
                self.task_error = str(r.info)
                # There seems to be an error, store for future reference
                self.save(update_fields=["task_state", "task_error"])
                return self.task_error
        return None

    def cancel_task(self):
        """Cancel task, if running"""
        r = self.get_async_result()
        if r:
            r.revoke()

    def task_worker(self):
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
        self.start_time = timezone.now()  # with timezone
        self.save()  # save such that any queries see this as running

        # actually run the task
        try:
            tracemalloc.start()
            tracemalloc.reset_peak()
            self.task_worker()
            size, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            self.task_state = TaskStateModel.SUCCESS
            self.task_memory = peak
            self.task_error = ""
        except CannotDetectFileFormat:
            self.task_state = TaskStateModel.FAILURE
            self.task_error = "The data file is of an unknown or unsupported format."
            self.task_traceback = traceback.format_exc()
        except Exception as exc:
            self.task_state = TaskStateModel.FAILURE
            # Store string representation of exception and traceback as user-reported
            # error string
            self.task_error = str(exc)
            self.task_traceback = traceback.format_exc()
            # we want a real exception here so celery's flower can show the task as
            # failure
            raise
        finally:
            # Store time stamp and save state to database
            self.end_time = timezone.now()  # with timezone
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
