from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from topobank.authorization.permissions import FULL, VIEW
from topobank.supplib.serializers import ModelRelatedField, UserField

from ...supplib.mixins import StrictFieldMixin
from ..models import Folder, Manifest


class ManifestV2Serializer(StrictFieldMixin, serializers.HyperlinkedModelSerializer):
    """Serializer for Manifest model."""
    class Meta:
        model = Manifest
        read_only_fields = [
            "id",
            "url",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ]
        fields = read_only_fields + [
            "folder",
            "filename",
            "file",
            "kind",
            "upload_confirmed",
            "upload_instructions",
        ]

    #
    # Self
    #
    url = serializers.HyperlinkedIdentityField(
        view_name="files:manifest-v2-detail", read_only=True
    )

    #
    # Hyperlinked resources
    #
    folder = ModelRelatedField(
        view_name="files:folder-api-detail", read_only=True
    )
    created_by = UserField(read_only=True)
    updated_by = UserField(read_only=True)

    file = serializers.FileField(read_only=True)
    kind = serializers.ChoiceField(choices=Manifest.FILE_KIND_CHOICES, read_only=True)
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


class ManifestV2CreateSerializer(StrictFieldMixin, serializers.HyperlinkedModelSerializer):
    """Serializer for creating Manifest model instances."""
    class Meta:
        model = Manifest
        required_fields = [
            "folder",
            "filename",
        ]
        fields = required_fields

    folder = serializers.HyperlinkedRelatedField(
        view_name="files:folder-api-detail", queryset=Folder.objects.all(),
        allow_null=True
    )

    def create(self, validated_data):
        # Get folder if specified
        folder = validated_data.get("folder", None)

        # UserUpdateMixin will set created_by and updated_by
        _ = validated_data.pop("owned_by")  # Ignored as Manifest doesnt have owned_by

        if folder is not None:
            # Set permissions based on folder if it exists
            validated_data['permissions'] = folder.permissions
        # PermissionSet will be created by manager if none is given

        instance = Manifest.objects.create(
            **validated_data
        )
        instance.grant_permission(self.context['request'].user, FULL)
        return instance

    def validate_folder(self, value):
        if value is not None:
            # Check permissions
            if not value.has_permission(self.context['request'].user, VIEW):
                raise serializers.ValidationError(
                    "Folder does not exist or you lack permission to access it."
                )
            # Check read-only status
            if value.read_only:
                raise serializers.ValidationError(
                    "Cannot create a manifest in a read-only folder."
                )
        return value

    def to_representation(self, instance):
        """Use ManifestV2Serializer for representation after creation."""
        return ManifestV2Serializer(
            instance,
            context=self.context,
        ).data
