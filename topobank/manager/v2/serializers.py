import pydantic
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.reverse import reverse
from tagulous.contrib.drf import TagRelatedManagerField

from ...files.models import Manifest
from ...organizations.models import Organization
from ...properties.serializers import PropertiesField
from ...supplib.serializers import PermissionsField, StrictFieldMixin
from ...taskapp.serializers import TaskStateModelSerializer
from ..models import Surface, Topography
from ..zip_model import ZipContainer


class TopographyV2Serializer(StrictFieldMixin, TaskStateModelSerializer):
    class Meta:
        model = Topography
        fields = [
            # Self
            "url",
            "id",
            # Auxiliary API endpoints
            "api",
            # Permissions
            "permissions",
            # Hyperlinked resources
            "surface_url",
            "creator_url",
            "datafile_url",
            "squeezed_datafile_url",
            "thumbnail_url",
            "attachments_url",
            "deepzoom_url",
            # Everything else
            "name",
            "datafile_format",
            "channel_names",
            "data_source",
            "description",
            "measurement_date",
            "size_editable",
            "size_x",
            "size_y",
            "unit_editable",
            "unit",
            "height_scale_editable",
            "height_scale",
            "has_undefined_data",
            "fill_undefined_data_mode",
            "detrend_mode",
            "resolution_x",
            "resolution_y",
            "bandwidth_lower",
            "bandwidth_upper",
            "short_reliability_cutoff",
            "is_periodic_editable",
            "is_periodic",
            "instrument_name",
            "instrument_type",
            "instrument_parameters",
            "is_metadata_complete",
            "creation_time",
            "modification_time",
            "task_duration",
            "task_error",
            "task_progress",
            "task_state",
            "tags",
        ]

    # Self
    url = serializers.HyperlinkedIdentityField(
        view_name="manager:topography-v2-detail", read_only=True
    )

    # Hyperlinked resources
    creator_url = serializers.HyperlinkedRelatedField(
        source="creator", view_name="users:user-v1-detail", read_only=True
    )
    surface_url = serializers.HyperlinkedRelatedField(
        source="surface",
        view_name="manager:surface-v2-detail",
        queryset=Surface.objects.all(),
    )
    datafile_url = serializers.HyperlinkedRelatedField(
        source="datafile", view_name="files:manifest-api-detail", read_only=True
    )
    squeezed_datafile_url = serializers.HyperlinkedRelatedField(
        source="squeezed_datafile",
        view_name="files:manifest-api-detail",
        read_only=True,
    )
    thumbnail_url = serializers.HyperlinkedRelatedField(
        source="thumbnail", view_name="files:manifest-api-detail", read_only=True
    )
    deepzoom_url = serializers.HyperlinkedRelatedField(
        source="deepzoom", view_name="files:folder-api-detail", read_only=True
    )
    attachments_url = serializers.HyperlinkedRelatedField(
        source="attachments", view_name="files:folder-api-detail", read_only=True
    )

    # Auxiliary API endpoints
    api = serializers.SerializerMethodField()

    # Permissions
    permissions = PermissionsField(read_only=True)

    # Everything else
    tags = TagRelatedManagerField(required=False)
    is_metadata_complete = serializers.SerializerMethodField()

    def validate(self, data):
        read_only_fields = []
        if self.instance is not None:
            if not self.instance.size_editable:
                if "size_x" in data:
                    read_only_fields += ["size_x"]
                if "size_y" in data:
                    read_only_fields += ["size_y"]
            if not self.instance.unit_editable:
                if "unit" in data:
                    read_only_fields += ["unit"]
            if not self.instance.height_scale_editable:
                if "unit" in data:
                    read_only_fields += ["height_scale"]
            if not self.instance.is_periodic_editable:
                if "is_periodic" in data:
                    read_only_fields += ["is_periodic"]
            if len(read_only_fields) > 0:
                s = ", ".join([f"`{name}`" for name in read_only_fields])
                raise serializers.ValidationError(
                    f"{s} is given by the data file and cannot be set"
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

    def get_is_metadata_complete(self, obj):
        return obj.is_metadata_complete

    def update(self, instance, validated_data):
        if "surface" in validated_data:
            raise serializers.ValidationError(
                {"message": "You cannot change the `surface` of a topography"}
            )
        try:
            return super().update(instance, validated_data)
        except pydantic.ValidationError as exc:
            # The kwargs that were provided do not match the function
            raise serializers.ValidationError({"message": str(exc)})


class SurfaceV2Serializer(StrictFieldMixin, serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Surface
        fields = [
            # Self
            "url",
            "id",
            # Auxiliary API endpoints
            "api",
            # Permissions
            "permissions",
            # Hyperlinked resources
            "creator_url",
            "owner_url",
            "attachments_url",
            # Everything else
            "name",
            "category",
            "description",
            "tags",
            "creation_time",
            "modification_time",
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
    creator_url = serializers.HyperlinkedRelatedField(
        source="creator", view_name="users:user-v1-detail", read_only=True
    )
    owner_url = serializers.HyperlinkedRelatedField(
        source="owner",
        view_name="organizations:organization-v1-detail",
        queryset=Organization.objects.all(),
        required=False,
    )
    attachments_url = serializers.HyperlinkedRelatedField(
        source="attachments", view_name="files:folder-api-detail", read_only=True
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
    """
    Serializer for ZipContainer model.
    """

    class Meta:
        model = ZipContainer
        fields = [
            # Self
            "url",
            "id",
            # Auxiliary API endpoints
            "api",
            # Permissions
            "permissions",
            # Hyperlinked resources
            "manifest_url",
            # Model fields
            "task_duration",
            "task_error",
            "task_progress",
            "task_state",
            "task_memory",
            "task_traceback",
            "celery_task_state",
            "self_reported_task_state",
            "creation_time",
            "modification_time",
        ]
        read_only_fields = ["creation_time", "modification_time"]

    # Self
    url = serializers.HyperlinkedIdentityField(
        view_name="manager:zip-container-v2-detail", read_only=True
    )

    # Auxiliary API endpoints
    api = serializers.SerializerMethodField()

    # Permissions
    permissions = PermissionsField()

    # The actual file
    manifest_url = serializers.HyperlinkedRelatedField(
        source="manifest",
        view_name="files:manifest-api-detail",
        queryset=Manifest.objects.all(),
    )

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
