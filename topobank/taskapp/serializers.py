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
    error = serializers.CharField(source="get_task_error", read_only=True)
    task_progress = serializers.FloatField(source="get_task_progress", read_only=True)
    task_state = serializers.CharField(source="get_task_state", read_only=True)
    celery_task_state = serializers.CharField(source="get_celery_state", read_only=True)
    self_reported_task_state = serializers.CharField(
        source="task_state", read_only=True
    )
