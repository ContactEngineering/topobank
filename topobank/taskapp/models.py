import tracemalloc

import celery.result
import celery.states
from celery.utils.log import get_task_logger

import django.db.models as models
from django.utils import timezone

from SurfaceTopography.Exceptions import CannotDetectFileFormat

_log = get_task_logger(__name__)


class TaskStateModel(models.Model):
    class Meta:
        abstract = True

    PENDING = 'pe'
    STARTED = 'st'
    RETRY = 're'
    FAILURE = 'fa'
    SUCCESS = 'su'
    NOTRUN = 'no'

    TASK_STATE_CHOICES = (
        (PENDING, 'pending'),
        (STARTED, 'started'),
        (RETRY, 'retry'),
        (FAILURE, 'failure'),
        (SUCCESS, 'success'),
        (NOTRUN, 'not run')
    )

    # Mapping Celery states to our state information. Everything not in the
    # list (e.g. custom Celery states) are interpreted as STARTED.
    _CELERY_STATE_MAP = {
        celery.states.SUCCESS: SUCCESS,
        celery.states.STARTED: STARTED,
        celery.states.PENDING: PENDING,
        celery.states.RETRY: RETRY,
        celery.states.FAILURE: FAILURE
    }

    # This is the Celery task id
    task_id = models.CharField(max_length=155, unique=True, null=True)
    # Django documentation discourages the use of null=True on a CharField. I'll use it here
    # nevertheless, because I need this values as argument to a function where None has
    # a special meaning (task not yet run).

    # This is the self-reported task state. It can differ from what Celery
    # knows about the task.
    task_state = models.CharField(max_length=7, choices=TASK_STATE_CHOICES, default=NOTRUN)

    # Maxmimum memory usage of the task
    task_memory = models.FloatField(null=True)

    # Any error information emitted from the task
    task_error = models.TextField(default='')

    # Time stamps
    creation_time = models.DateTimeField(null=True)
    start_time = models.DateTimeField(null=True)
    end_time = models.DateTimeField(null=True)

    @property
    def duration(self):
        """Returns duration of computation or None if not finished yet.

        Does not take into account the queue time.

        :return: Returns datetime.timedelta or None
        """
        if self.end_time is None or self.start_time is None:
            return None

        return self.end_time - self.start_time

    def get_celery_state(self):
        """Return the state of the task as reported by Celery"""
        if self.task_id is None:
            # Cannot get the state
            return TaskStateModel.NOTRUN
        r = celery.result.AsyncResult(self.task_id)
        try:
            return self._CELERY_STATE_MAP[r.state]
        except KeyError:
            # Everything else (e.g. a custom state such as 'PROGRESS') is interpreted as a running task
            return TaskStateModel.STARTED

    def get_task_progress(self):
        """Return progress of task, if running"""
        if self.task_id is None:
            return None
        r = celery.result.AsyncResult(self.task_id)
        if isinstance(r.info, Exception):
            raise r.info  # The Celery process failed with some specific exception, reraise here
        else:
            return r.info

    def get_error(self):
        """Return a string representation of any error occurred during task execution"""
        # Return self-reported task error, if any
        if self.task_error:
            return self.task_error
        # If there is none, check Celery
        if self.task_id is None:
            return None
        r = celery.result.AsyncResult(self.task_id)
        if isinstance(r.info, Exception):
            return str(r.info)
        else:
            # No error occurred
            return None

    def cancel_task(self):
        """Cancel task, if running"""
        if self.task_id is not None:
            r = celery.result.AsyncResult(self.task_id)
            r.revoke()

    def task_worker(self):
        """The actual task"""
        raise NotImplementedError

    def run_task(self, celery_task, *args, **kwargs):
        """Execute the task worker and store states to database"""
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
            self.task_error = ''
        except CannotDetectFileFormat:
            self.task_state = TaskStateModel.FAILURE
            self.task_error = 'The data file is of an unknown or unsupported format.'
        except Exception as exc:
            self.task_state = TaskStateModel.FAILURE
            self.task_error = str(exc)  # store string representation of exception as user-reported error string
            # we want a real exception here so celery's flower can show the task as failure
            raise
        finally:
            # Store time stamp and save state to database
            self.end_time = timezone.now()  # with timezone
            self.save()


class Dependency(models.Model):
    """A dependency of analysis results, e.g. "SurfaceTopography", "topobank"
    """

    class Meta:
        db_table = 'analysis_dependency'  # This used to be part of the analysis app

    # this is used with "import":
    import_name = models.CharField(max_length=30, unique=True)

    def __str__(self):
        return self.import_name


class Version(models.Model):
    """
    A specific version of a dependency.
    Part of a configuration.
    """

    # TODO After upgrade to Django 2.2, use contraints: https://docs.djangoproject.com/en/2.2/ref/models/constraints/
    class Meta:
        db_table = 'analysis_version'  # This used to be part of the analysis app
        unique_together = (('dependency', 'major', 'minor', 'micro', 'extra'),)

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
    """For keeping track which versions were used for an analysis.
    """

    class Meta:
        db_table = 'analysis_configuration'  # This used to be part of the analysis app

    valid_since = models.DateTimeField(auto_now_add=True)
    versions = models.ManyToManyField(Version)

    def __str__(self):
        versions = [str(v) for v in self.versions.all()]
        return f"Valid since: {self.valid_since}, versions: {versions}"
