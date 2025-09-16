import logging

from rest_framework import serializers

from ..supplib.serializers import StrictFieldMixin
from .models import Folder, Manifest

_log = logging.getLogger(__name__)


class ManifestSerializer(StrictFieldMixin, serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Manifest
        fields = [
            "id",
            "url",
            "filename",
            "file",
            "folder",
            "kind",
            "created",
            "updated",
            "upload_confirmed",
            "uploaded_by",
            "upload_instructions",
        ]

    url = serializers.HyperlinkedIdentityField(
        view_name="files:manifest-api-detail", read_only=True
    )
    file = serializers.FileField(read_only=True)
    folder = serializers.HyperlinkedRelatedField(
        view_name="files:folder-api-detail", queryset=Folder.objects.all()
    )
    kind = serializers.ChoiceField(choices=Manifest.FILE_KIND_CHOICES, read_only=True)
    created = serializers.DateTimeField(read_only=True)
    updated = serializers.DateTimeField(read_only=True)
    upload_confirmed = serializers.DateTimeField(read_only=True)
    uploaded_by = serializers.HyperlinkedRelatedField(
        view_name="users:user-v1-detail", read_only=True
    )
    upload_instructions = serializers.SerializerMethodField()

    def __init__(self, instance=None, data=serializers.empty, **kwargs):
        if instance:
            instance.exists()  # Sets the actual file if not yet done
        super().__init__(instance=instance, data=data, **kwargs)

    def get_upload_instructions(self, obj: Manifest):
        return None if obj.exists() else obj.get_upload_instructions()
