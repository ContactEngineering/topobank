import django.db.models as models

import celery.result
import celery.states


class TaskStateModel(models.Model):
    class Meta:
        abstract = True

    PENDING = 'pe'
    STARTED = 'st'
    RETRY = 're'
    FAILURE = 'fa'
    SUCCESS = 'su'

    TASK_STATE_CHOICES = (
        (PENDING, 'pending'),
        (STARTED, 'started'),
        (RETRY, 'retry'),
        (FAILURE, 'failure'),
        (SUCCESS, 'success'),
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

    # This is the self-reported task state. It can differ from what Celery
    # knows about the task.
    task_state = models.CharField(max_length=7, choices=TASK_STATE_CHOICES)

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
        """Return the state of the task reported by Celery"""
        if self.task_id is None:
            # Cannot get the state
            return None
        r = celery.result.AsyncResult(self.task_id)
        try:
            return self._CELERY_STATE_MAP[r.state]
        except KeyError:
            # Everything else (e.g. a custom state such as 'PROGRESS') is interpreted as a running task
            return TaskStateMixin.STARTED

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
        """Return a string representation of any error"""
        if self.task_id is None:
            return None
        r = celery.result.AsyncResult(self.task_id)
        if isinstance(r.info, Exception):
            return (str(r.info))
        else:
            # No error occurred
            return None

    def cancel_task(self):
        # Cancel possibly running task
        if self.task_id is not None:
            r = celery.result.AsyncResult(self.task_id)
            r.revoke()
