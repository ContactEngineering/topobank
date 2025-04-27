from rest_framework import serializers

from ...supplib.serializers import StrictFieldMixin
from ...taskapp.serializers import TaskStateModelSerializer
from ..models import ZipContainer


class ZipContainerSerializer(StrictFieldMixin, TaskStateModelSerializer):
    """
    Serializer for ZipContainer model.
    """

    class Meta:
        model = ZipContainer
        fields = [
            "url",
            "id",
            "manifest",
            "duration",
            "error",
            "task_progress",
            "task_state",
            "task_memory",
            "celery_task_state",
            "self_reported_task_state",
        ]
        read_only_fields = ["created_at", "updated_at", "owner"]

    # Self
    url = serializers.HyperlinkedIdentityField(
        view_name="manager:zip-container-v2-detail", read_only=True
    )
