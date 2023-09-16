import logging

import celery.result
import celery.states

import django.db.models as models
from django.utils import timezone

from rest_framework import serializers

from SurfaceTopography.Exceptions import CannotDetectFileFormat

_log = logging.getLogger(__name__)


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
            self.task_worker()
            self.task_state = TaskStateModel.SUCCESS
        except CannotDetectFileFormat as exc:
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


class TaskStateModelSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        abstract = True
        model = TaskStateModel
        fields = ['duration', 'error', 'task_progress', 'task_state']

    duration = serializers.SerializerMethodField()
    error = serializers.SerializerMethodField()
    task_state = serializers.SerializerMethodField()
    task_progress = serializers.SerializerMethodField()

    def get_duration(self, obj):
        return obj.duration

    def get_error(self, obj):
        return obj.get_error()

    def get_task_progress(self, obj):
        task_state = self.get_task_state(obj)
        if task_state == TaskStateModel.STARTED:
            return obj.get_task_progress()
        elif task_state == TaskStateModel.SUCCESS:
            return 1.0
        else:
            return 0.0

    def get_task_state(self, obj):
        """
        Return the most likely state of the task from the self-reported task
        information in the database and the information obtained from Celery.
        """
        # This is self-reported by the task runner
        self_reported_task_state = obj.task_state
        # This is what Celery reports back
        celery_task_state = obj.get_celery_state()

        if celery_task_state is None:
            # There is no Celery state, possibly because the Celery task has not yet been created
            return self_reported_task_state

        if self_reported_task_state == celery_task_state:
            # We're good!
            return self_reported_task_state
        else:
            if self_reported_task_state == TaskStateModel.SUCCESS:
                # Something is wrong, but we return success if the task self-reports success.
                _log.info(f"The object with id {obj.id} self-reported the state '{self_reported_task_state}', "
                          f"but Celery reported '{celery_task_state}'. I am returning a success.")
                return TaskStateModel.SUCCESS
            elif celery_task_state == TaskStateModel.FAILURE:
                # Celery seems to think this task failed, we trust it as the self-reported state will
                # be unreliable in this case.
                _log.info(f"The object with id {obj.id} self-reported the state '{self_reported_task_state}', "
                          f"but Celery reported '{celery_task_state}'. I am returning a failure.")
                return TaskStateModel.FAILURE
            else:
                # In all other cases, we trust the self-reported state.
                _log.info(f"The object with id {obj.id} self-reported the state '{self_reported_task_state}', "
                          f"but Celery reported '{celery_task_state}'. I am returning the self-reported state.")
                return self_reported_task_state
