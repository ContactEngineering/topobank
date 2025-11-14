import pydantic
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.reverse import reverse
from tagulous.contrib.drf import TagRelatedManagerField

from ...properties.serializers import PropertiesField
from ...supplib.serializers import (
    ManifestField,
    ModelRelatedField,
    OrganizationField,
    PermissionsField,
    StrictFieldMixin,
    UserField,
)
from ...taskapp.serializers import TaskStateModelSerializer
from ..models import Surface, Topography
from ..zip_model import ZipContainer


class TopographyV2Serializer(StrictFieldMixin, TaskStateModelSerializer):
    """v2 Serializer for Topography model."""
    class Meta:
        model = Topography
        read_only_fields = [
            "url",
            "id",
            "api",
            "permissions",
            "created_by",
            "updated_by",
            "owned_by",
            "datafile",
            "squeezed_datafile",
            "thumbnail",
            "deepzoom",
            "datafile_format",
            "channel_names",
            "data_source",
            "created_at",
            "updated_at",
            "task_duration",
            "task_error",
            "task_progress",
            "task_state",
            "size_editable",
            "unit_editable",
            "height_scale_editable",
            "has_undefined_data",
            "is_periodic_editable",
            "is_metadata_complete",
        ]
        fields = read_only_fields + [
            "attachments",
            "surface",
            "name",
            "description",
            "measurement_date",
            "size_x",
            "size_y",
            "unit",
            "height_scale",
            "fill_undefined_data_mode",
            "detrend_mode",
            "resolution_x",
            "resolution_y",
            "bandwidth_lower",
            "bandwidth_upper",
            "short_reliability_cutoff",
            "is_periodic",
            "instrument_name",
            "instrument_type",
            "instrument_parameters",
            "tags",
        ]

    # Self
    url = serializers.HyperlinkedIdentityField(
        view_name="manager:topography-v2-detail", read_only=True
    )

    # Hyperlinked resources
    created_by = UserField(read_only=True)
    updated_by = UserField(read_only=True)
    owned_by = OrganizationField(read_only=True)
    surface = ModelRelatedField(
        view_name="manager:surface-v2-detail",
        queryset=Surface.objects.all(),
        required=True
    )
    datafile = ManifestField(read_only=True)
    squeezed_datafile = ManifestField(read_only=True)
    thumbnail = ManifestField(read_only=True)
    deepzoom = ModelRelatedField(
        view_name="files:folder-api-detail", read_only=True
    )
    attachments = ModelRelatedField(
        view_name="files:folder-api-detail", read_only=True
    )

    # Auxiliary API endpoints
    api = serializers.SerializerMethodField()

    # Permissions
    permissions = PermissionsField(read_only=True)

    # Everything else
    tags = TagRelatedManagerField(required=False)
    is_metadata_complete = serializers.SerializerMethodField()

    def validate(self, data):
        if self.instance is None:
            return super().validate(data)

        # Map fields to their editability checks
        editability_checks = {
            'size_x': self.instance.size_editable,
            'size_y': self.instance.size_editable,
            'unit': self.instance.unit_editable,
            'height_scale': self.instance.height_scale_editable,
            'is_periodic': self.instance.is_periodic_editable,
        }

        # Find fields that are in data but not editable
        read_only_fields = [
            field for field, is_editable in editability_checks.items()
            if field in data and not is_editable
        ]

        if read_only_fields:
            s = ", ".join([f"`{name}`" for name in read_only_fields])
            raise serializers.ValidationError(
                f"{s} {'is' if len(read_only_fields) == 1 else 'are'} given by the data file and cannot be set"
            )

        return super().validate(data)

    @extend_schema_field(
        {
            "type": "object",
            "properties": {
                "force_inspect": {"type": "string"},
            },
            "required": ["force_inspect"],
        }
    )
    def get_api(self, obj: Topography) -> dict:
        return {
            "force_inspect": reverse(
                "manager:force-inspect",
                kwargs={"pk": obj.id},
                request=self.context["request"],
            ),
        }

    def get_is_metadata_complete(self, obj: Topography) -> bool:
        return obj.is_metadata_complete

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except pydantic.ValidationError as exc:
            # The kwargs that were provided do not match the function
            raise serializers.ValidationError({"message": str(exc)})


class SurfaceV2Serializer(StrictFieldMixin, serializers.HyperlinkedModelSerializer):
    """v2 Serializer for Surface model."""
    class Meta:
        model = Surface
        read_only_fields = [
            "url",
            "id",
            "api",
            "permissions",
            "created_by",
            "updated_by",
            "owned_by",
            "created_at",
            "updated_at",
        ]
        fields = read_only_fields + [
            "attachments",
            "name",
            "category",
            "description",
            "tags",
            "properties",
        ]

    # Self
    url = serializers.HyperlinkedIdentityField(
        view_name="manager:surface-v2-detail", read_only=True
    )

    # Auxiliary API endpoints
    api = serializers.SerializerMethodField()

    # Permissions
    permissions = PermissionsField(read_only=True)

    # Hyperlinked resources
    created_by = UserField(read_only=True)
    updated_by = UserField(read_only=True)
    owned_by = OrganizationField(read_only=True)

    attachments = ModelRelatedField(
        view_name="files:folder-api-detail", read_only=True
    )

    # Everything else
    properties = PropertiesField(required=False)
    tags = TagRelatedManagerField(required=False)

    @extend_schema_field(
        {
            "type": "object",
            "properties": {
                "async_download": {"type": "string"},
                "topographies": {"type": "string"},
            },
            "required": ["async_download", "topographies"],
        }
    )
    def get_api(self, obj: Surface) -> dict:
        request = self.context["request"]
        return {
            "async_download": reverse(
                "manager:surface-download-v2",
                kwargs={"surface_ids": obj.id},
                request=request,
            ),
            "topographies": reverse("manager:topography-v2-list", request=request)
            + f"?surface={obj.id}",
        }


class ZipContainerV2Serializer(StrictFieldMixin, TaskStateModelSerializer):
    """v2 Serializer for ZipContainer model."""

    class Meta:
        model = ZipContainer
        read_only_fields = [
            "url",
            "id",
            "api",
            "permissions",
            "task_duration",
            "task_error",
            "task_progress",
            "task_state",
            "task_memory",
            "task_traceback",
            "celery_task_state",
            "self_reported_task_state",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        fields = read_only_fields + [
            "manifest",
        ]

    # Self
    url = serializers.HyperlinkedIdentityField(
        view_name="manager:zip-container-v2-detail", read_only=True
    )

    # Auxiliary API endpoints
    api = serializers.SerializerMethodField()

    # Permissions
    permissions = PermissionsField(read_only=True)

    # Hyperlinked resources
    created_by = UserField(read_only=True)
    updated_by = UserField(read_only=True)

    # The actual file
    manifest = ManifestField(read_only=True)

    @extend_schema_field(
        {
            "type": "object",
            "properties": {
                "upload_finished": {"type": "string"},
            },
            "required": ["upload_finished"],
        }
    )
    def get_api(self, obj: ZipContainer) -> dict:
        request = self.context["request"]
        return {
            "upload_finished": reverse(
                "manager:zip-upload-finish-v2",
                kwargs={"pk": obj.id},
                request=request,
            )
        }
