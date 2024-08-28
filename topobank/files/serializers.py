import logging

from rest_framework import serializers

from .models import Manifest

_log = logging.getLogger(__name__)


class ManifestSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Manifest
        fields = [
            "url",
            "filename",
            "file",
            "kind",
            "created",
            "updated",
            "upload_finished",
            "uploaded_by",
            "upload_instructions",
        ]

    url = serializers.HyperlinkedIdentityField(
        view_name="files:manifest-api-detail", read_only=True
    )
    file = serializers.FileField(read_only=True)
    kind = serializers.ChoiceField(choices=Manifest.FILE_KIND_CHOICES)
    created = serializers.DateTimeField(read_only=True)
    updated = serializers.DateTimeField(read_only=True)
    upload_finished = serializers.DateTimeField(read_only=True)
    uploaded_by = serializers.HyperlinkedRelatedField(
        view_name="users:user-api-detail", read_only=True
    )
    upload_instructions = serializers.SerializerMethodField()

    def get_upload_instructions(self, obj: Manifest):
        if not obj.file:
            return obj.get_upload_instructions()
        else:
            return None
