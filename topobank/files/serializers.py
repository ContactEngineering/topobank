import logging

from rest_framework import serializers

from ..manager.models import Surface, Topography
from .models import Folder, Manifest

_log = logging.getLogger(__name__)


class FileUploadSerializer(serializers.Serializer):
    surface = serializers.HyperlinkedRelatedField(
        view_name="manager:surface-api-detail",
        queryset=Surface.objects.all(),
        required=False,
    )
    topography = serializers.HyperlinkedRelatedField(
        view_name="manager:topography-api-detail",
        queryset=Topography.objects.all(),
        required=False,
    )
    kind = serializers.ChoiceField(choices=Manifest.FILE_KIND_CHOICES)
    file_name = serializers.CharField()
    file_type = serializers.CharField(allow_blank=True)

    def validate(self, data):
        surface_value = data.get("surface")
        topography_value = data.get("topography")

        if surface_value is None and topography_value is None:
            raise serializers.ValidationError(
                "Exactly one of surface or topography must be provided."
            )
        elif surface_value is not None and topography_value is not None:
            raise serializers.ValidationError(
                "Only one of surface or topography should be provided, not both."
            )

        if surface_value is not None:
            data["parent"], _ = Folder.objects.get_or_create(surface=surface_value)
            del data["surface"]
        elif topography_value is not None:
            data["parent"], _ = Folder.objects.get_or_create(
                topography=topography_value
            )
            del data["topography"]

        return data


class FileManifestSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Manifest
        fields = [
            "url",
            "file_name",
            "file",
            "kind",
            "created",
            "updated",
            "creator_name",
        ]

    url = serializers.HyperlinkedIdentityField(
        view_name="files:manifest-api-detail", read_only=True
    )
    file = serializers.FileField(read_only=True)
    kind = serializers.ChoiceField(choices=Manifest.FILE_KIND_CHOICES)
    created = serializers.DateTimeField(read_only=True)
    updated = serializers.DateTimeField(read_only=True)
    creator_name = serializers.SerializerMethodField()

    def get_creator_name(self, obj):
        return obj.uploaded_by.name
