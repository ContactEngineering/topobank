from celery.utils.log import get_task_logger
from rest_framework import serializers

from .models import TaskStateModel

_log = get_task_logger(__name__)


class TaskStateModelSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        abstract = True
        model = TaskStateModel
        fields = [
            "duration",
            "error",
            "task_progress",
            "task_state",
            "task_memory",
            "celery_task_state",
            "self_reported_task_state",
        ]

    default_error_messages = {"read_only": "This field is read only"}

    duration = serializers.DurationField(read_only=True)
    error = serializers.CharField(source="get_error", read_only=True)
    task_state = serializers.SerializerMethodField()
    task_progress = serializers.FloatField(source="get_task_progress", read_only=True)
    celery_task_state = serializers.CharField(source="get_celery_state", read_only=True)
    self_reported_task_state = serializers.CharField(source="task_state", read_only=True)

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
                    f"The object with id {obj.id} self-reported the state "
                    f"'{self_reported_task_state}', but Celery reported "
                    f"'{celery_task_state}'. I am returning a success."
                )
                return TaskStateModel.SUCCESS
            elif celery_task_state == TaskStateModel.FAILURE:
                # Celery seems to think this task failed, we trust it as the
                # self-reported state will be unreliable in this case.
                _log.info(
                    f"The object with id {obj.id} self-reported the state "
                    f"'{self_reported_task_state}', but Celery reported "
                    f"'{celery_task_state}'. I am returning a failure."
                )
                return TaskStateModel.FAILURE
            else:
                # In all other cases, we trust the self-reported state.
                _log.info(
                    f"The object with id {obj.id} self-reported the state "
                    f"'{self_reported_task_state}', but Celery reported "
                    f"'{celery_task_state}'. I am returning the self-reported state."
                )
                return self_reported_task_state
