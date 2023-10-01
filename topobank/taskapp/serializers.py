from rest_framework import serializers

from celery.utils.log import get_task_logger

from .models import TaskStateModel

_log = get_task_logger(__name__)


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
