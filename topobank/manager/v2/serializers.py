from rest_framework import serializers

from ...files.models import Manifest
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
            "task_duration",
            "task_error",
            "task_progress",
            "task_state",
            "task_memory",
            "task_traceback",
            "celery_task_state",
            "self_reported_task_state",
        ]
        read_only_fields = ["created_at", "updated_at", "owner"]

    # Self
    url = serializers.HyperlinkedIdentityField(
        view_name="manager:zip-container-v2-detail", read_only=True
    )

    # The actual file
    manifest = serializers.HyperlinkedRelatedField(
        view_name="files:manifest-api-detail", queryset=Manifest.objects.all()
    )
