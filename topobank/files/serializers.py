import logging

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from ..supplib.serializers import StrictFieldMixin
from .models import Folder, Manifest

_log = logging.getLogger(__name__)


class ManifestSerializer(StrictFieldMixin, serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Manifest
        fields = [
            # Self
            "url",
            "id",
            # Hyperlinked resources
            "folder",  # should become folder_url in v2
            "uploaded_by",  # should become upload_user_url in v2
            # Model fields
            "filename",
            "file",
            "kind",
            "created",  # should become creation_time in v2
            "updated",  # should become modification_time in v2
            "upload_confirmed",  # should become upload_confirmation_time in v2
            "upload_instructions",
        ]

    #
    # Self
    #
    url = serializers.HyperlinkedIdentityField(
        view_name="files:manifest-api-detail", read_only=True
    )

    #
    # Hyperlinked resources
    #
    folder = serializers.HyperlinkedRelatedField(
        view_name="files:folder-api-detail", queryset=Folder.objects.all()
    )
    uploaded_by = serializers.HyperlinkedRelatedField(
        view_name="users:user-v1-detail", read_only=True
    )

    file = serializers.FileField(read_only=True)
    kind = serializers.ChoiceField(choices=Manifest.FILE_KIND_CHOICES, read_only=True)
    created = serializers.DateTimeField(read_only=True)
    updated = serializers.DateTimeField(read_only=True)
    upload_confirmed = serializers.DateTimeField(read_only=True)
    upload_instructions = serializers.SerializerMethodField()

    def __init__(self, instance=None, data=serializers.empty, **kwargs):
        if instance:
            instance.exists()  # Sets the actual file if not yet done
        super().__init__(instance=instance, data=data, **kwargs)

    @extend_schema_field(
        {
            "type": "object",
            "properties": {
                "method": {"type": "string"},
                "url": {"type": "string"},
                "fields": {"type": "object"},
            },
            "required": ["method", "url"],
        }
    )
    def get_upload_instructions(self, obj: Manifest) -> dict | None:
        return None if obj.exists() else obj.get_upload_instructions()
