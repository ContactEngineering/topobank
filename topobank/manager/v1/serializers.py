import logging

import pydantic
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.reverse import reverse
from tagulous.contrib.drf import TagRelatedManagerField

from ...files.serializers import ManifestSerializer
from ...manager.models import Surface, Tag, Topography
from ...properties.serializers import PropertiesField
from ...supplib.serializers import StrictFieldMixin
from ...taskapp.serializers import TaskStateModelSerializer

_log = logging.getLogger(__name__)


class TagSerializer(StrictFieldMixin, serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Tag
        fields = [
            "url",
            "api",
            "id",
            "name",
            "children",
            "path",
            "label",
            "slug",
            "level",
            "count",
        ]

    url = serializers.HyperlinkedIdentityField(
        view_name="manager:tag-api-detail", lookup_field="name", read_only=True
    )
    api = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()

    @extend_schema_field(
        {
            "type": "object",
            "properties": {
                "set_permissions": {"type": "string"},
                "download": {"type": "string"},
                "async_download": {"type": "string"},
            },
            "required": ["set_permissions", "download", "async_download"],
        }
    )
    def get_api(self, obj: Tag) -> dict:
        return {
            "set_permissions": reverse(
                "manager:set-tag-permissions",
                kwargs={"name": obj.name},
                request=self.context["request"],
            ),
            "download": reverse(
                "manager:tag-download",
                kwargs={"name": obj.name},
                request=self.context["request"],
            ),
            "async_download": reverse(
                "manager:tag-download-v2",
                kwargs={"name": obj.name},
                request=self.context["request"],
            ),
        }

    def get_children(self, obj: Tag):
        request = self.context["request"]
        obj.authorize_user(request.user, "view")
        return obj.get_children()


class TopographySerializer(StrictFieldMixin, TaskStateModelSerializer):
    class Meta:
        model = Topography
        fields = [
            # Self
            "url",
            "id",
            # Auxiliary API endpoints
            "api",
            # Deprecations
            "surface",
            "creator",
            "datafile",
            "squeezed_datafile",
            "thumbnail",
            "attachments",
            "deepzoom",
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
            "creation_datetime",
            "modification_datetime",
            "task_duration",
            "task_error",
            "task_progress",
            "task_state",
            "tags",
            "permissions",
        ]

    # Self
    url = serializers.HyperlinkedIdentityField(
        view_name="manager:topography-api-detail", read_only=True
    )

    # Deprecated
    creator = serializers.HyperlinkedRelatedField(
        view_name="users:user-v1-detail", read_only=True
    )
    surface = serializers.HyperlinkedRelatedField(
        view_name="manager:surface-api-detail", queryset=Surface.objects.all()
    )
    datafile = ManifestSerializer(required=False)
    squeezed_datafile = ManifestSerializer(required=False)
    thumbnail = ManifestSerializer(required=False)
    deepzoom = serializers.HyperlinkedRelatedField(
        view_name="files:folder-api-detail", read_only=True
    )
    attachments = serializers.HyperlinkedRelatedField(
        view_name="files:folder-api-detail", read_only=True
    )

    # These fields have been renamed in the model
    creation_datetime = serializers.DateTimeField(
        source="creation_time", read_only=True
    )
    modification_datetime = serializers.DateTimeField(
        source="modification_time", read_only=True
    )

    # Auxiliary API endpoints
    api = serializers.SerializerMethodField()

    # Everything else
    tags = TagRelatedManagerField(required=False)
    is_metadata_complete = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    def validate(self, data: dict) -> dict:
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

    def get_is_metadata_complete(self, obj: Topography) -> bool:
        return obj.is_metadata_complete

    def get_permissions(self, obj: Topography) -> dict:
        request = self.context["request"]
        current_user = request.user
        user_permissions = obj.permissions.user_permissions.all()
        return {
            "current_user": {
                "user": current_user.get_absolute_url(request),
                "permission": obj.get_permission(current_user),
            },
            "other_users": [
                {
                    "user": perm.user.get_absolute_url(request),
                    "permission": perm.allow,
                }
                for perm in user_permissions
                if perm.user != current_user
            ],
        }

    def update(self, instance: Topography, validated_data: dict):
        if "surface" in validated_data:
            raise serializers.ValidationError(
                {"message": "You cannot change the `surface` of a topography"}
            )
        try:
            return super().update(instance, validated_data)
        except pydantic.ValidationError as exc:
            # The kwargs that were provided do not match the function
            raise serializers.ValidationError({"message": str(exc)})


class SurfaceSerializer(StrictFieldMixin, serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Surface
        fields = [
            # Self
            "url",
            "id",
            # Auxiliary API endpoints
            "api",
            # Deprecations
            "creator",
            "topography_set",
            "attachments",
            "topographies",
            # Everything else
            "name",
            "category",
            "description",
            "tags",
            "creation_datetime",
            "modification_datetime",
            "permissions",
            "properties",
        ]

    # Self
    url = serializers.HyperlinkedIdentityField(
        view_name="manager:surface-api-detail", read_only=True
    )

    # Auxiliary API endpoints
    api = serializers.SerializerMethodField()

    # Deprecations
    creator = serializers.HyperlinkedRelatedField(
        view_name="users:user-v1-detail", read_only=True
    )
    topography_set = TopographySerializer(many=True, read_only=True)
    attachments = serializers.HyperlinkedRelatedField(
        view_name="files:folder-api-detail", read_only=True
    )
    topographies = serializers.SerializerMethodField()

    # Everything else
    properties = PropertiesField(required=False)
    tags = TagRelatedManagerField(required=False)
    permissions = serializers.SerializerMethodField()

    # These fields have been renamed in the model
    creation_datetime = serializers.DateTimeField(
        source="creation_time", read_only=True
    )
    modification_datetime = serializers.DateTimeField(
        source="modification_time", read_only=True
    )

    @extend_schema_field(
        {
            "type": "object",
            "properties": {
                "set_permissions": {"type": "string"},
                "download": {"type": "string"},
                "async_download": {"type": "string"},
            },
            "required": ["set_permissions", "download", "async_download"],
        }
    )
    def get_api(self, obj: Surface) -> dict:
        return {
            "set_permissions": reverse(
                "manager:set-surface-permissions",
                kwargs={"pk": obj.id},
                request=self.context["request"],
            ),
            "download": reverse(
                "manager:surface-download",
                kwargs={"surface_ids": obj.id},
                request=self.context["request"],
            ),
            "async_download": reverse(
                "manager:surface-download-v2",
                kwargs={"surface_ids": obj.id},
                request=self.context["request"],
            ),
        }

    def get_permissions(self, obj):
        request = self.context["request"]
        current_user = request.user
        user_permissions = obj.permissions.user_permissions.all()
        return {
            "current_user": {
                "user": current_user.get_absolute_url(request),
                "permission": obj.get_permission(current_user),
            },
            "other_users": [
                {
                    "user": perm.user.get_absolute_url(request),
                    "permission": perm.allow,
                }
                for perm in user_permissions
                if perm.user != current_user
            ],
        }

    def get_topographies(self, obj):
        request = self.context["request"]
        return (
            f"{reverse('manager:topography-api-list', request=request)}"
            f"?surface={obj.id}"
        )

    # def get_topographies_url(self, obj):
    #     request = self.context["request"]
    #     return (
    #         f"{reverse('manager:topography-api-list', request=request)}"
    #         f"?surface={obj.id}"
    #     )
