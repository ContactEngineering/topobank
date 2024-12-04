import logging

import pydantic
from django.db import transaction
from rest_framework import serializers
from rest_framework.reverse import reverse
from tagulous.contrib.drf import TagRelatedManagerField

from ..files.serializers import ManifestSerializer
from ..properties.models import Property
from ..supplib.serializers import StrictFieldMixin
from ..taskapp.serializers import TaskStateModelSerializer
from .models import Surface, Tag, Topography

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

    def get_api(self, obj):
        return {
            "self": obj.get_absolute_url(self.context["request"]),
            "set_permissions": reverse(
                "manager:set-tag-permissions",
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
            # Hyperlinked resources
            # "surface_url",
            # "creator_url",
            # "datafile_url",
            # "squeezed_datafile_url",
            # "thumbnail_url",
            # "attachments_url",
            # "deepzoom_url",
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
            "duration",
            "error",
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
        view_name="users:user-api-detail", read_only=True
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

    # Hyperlinked resources
    # creator_url = serializers.HyperlinkedRelatedField(
    #     source="creator", view_name="users:user-api-detail", read_only=True
    # )
    # surface_url = serializers.HyperlinkedRelatedField(
    #     source="surface", view_name="manager:surface-api-detail", queryset=Surface.objects.all()
    # )
    # datafile_url = serializers.HyperlinkedRelatedField(
    #     source="datafile", view_name="files:manifest-api-detail", read_only=True
    # )
    # squeezed_datafile_url = serializers.HyperlinkedRelatedField(
    #     source="squeezed_datafile", view_name="files:manifest-api-detail", read_only=True
    # )
    # thumbnail_url = serializers.HyperlinkedRelatedField(
    #     source="thumbnail", view_name="files:manifest-api-detail", read_only=True
    # )
    # deepzoom_url = serializers.HyperlinkedRelatedField(
    #     source="deepzoom", view_name="files:folder-api-detail", read_only=True
    # )
    # attachments_url = serializers.HyperlinkedRelatedField(
    #     source="attachments", view_name="files:folder-api-detail", read_only=True
    # )

    # Auxiliary API endpoints
    api = serializers.SerializerMethodField()

    # Everything else
    tags = TagRelatedManagerField(required=False)
    is_metadata_complete = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

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

    def get_api(self, obj):
        return {
            "self": obj.get_absolute_url(self.context["request"]),
            "force_inspect": reverse(
                "manager:force-inspect",
                kwargs={"pk": obj.id},
                request=self.context["request"],
            ),
        }

    def get_is_metadata_complete(self, obj):
        return obj.is_metadata_complete

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


class ValueField(serializers.Field):
    def to_representation(self, value):
        return value

    def to_internal_value(self, data):
        return data


class PropertiesField(serializers.Field):
    def to_representation(self, value):
        ret = {}
        for prop in value.all():
            ret[prop.name] = {"value": prop.value}
            if prop.unit is not None:
                ret[prop.name]["unit"] = str(prop.unit)
        return ret

    def to_internal_value(self, data: dict[str, dict[str, str]]):
        surface: Surface = self.root.instance
        with (
            transaction.atomic()
        ):  # NOTE: This is probably not needed because django wraps views in a transaction.
            # WARNING: with the current API design surfaces can only be created with no properties.
            if surface is not None:
                surface.properties.all().delete()
                for property in data:
                    # NOTE: Validate that a numeric value has a unit
                    if (
                        isinstance(data[property]["value"], (int, float))
                        and "unit" not in data[property]
                    ):
                        raise serializers.ValidationError(
                            {property: "numeric properties must have a unit"}
                        )
                    elif (
                        isinstance(data[property]["value"], str)
                        and "unit" in data[property]
                    ):
                        raise serializers.ValidationError(
                            {property: "categorical properties must not have a unit"}
                        )

                    Property.objects.create(
                        surface=surface,
                        name=property,
                        value=data[property]["value"],
                        unit=data[property].get("unit"),
                    )

                return self.root.instance.properties.all()
        return []


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
            # Hyperlinked resources
            # "creator_url",
            # "topographies_url",
            # "attachments_url",
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
        view_name="users:user-api-detail", read_only=True
    )
    topography_set = TopographySerializer(many=True, read_only=True)
    attachments = serializers.HyperlinkedRelatedField(
        view_name="files:folder-api-detail", read_only=True
    )
    topographies = serializers.SerializerMethodField()

    # Hyperlinked resources
    # creator_url = serializers.HyperlinkedRelatedField(
    #     view_name="users:user-api-detail", read_only=True
    # )
    # topographies_url = serializers.SerializerMethodField()
    # attachments_url = serializers.HyperlinkedRelatedField(
    #     view_name="files:folder-api-detail", read_only=True
    # )

    # Everything else
    properties = PropertiesField(required=False)
    tags = TagRelatedManagerField(required=False)
    permissions = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        optional_fields = [
            ("children", "topography_set"),
            ("permissions", "permissions"),
        ]
        for option, field in optional_fields:
            param = self.context["request"].query_params.get(option)
            requested = param is not None and param.lower() in ["yes", "true"]
            if not requested:
                self.fields.pop(field)

    def get_api(self, obj):
        return {
            "self": obj.get_absolute_url(self.context["request"]),
            "set_permissions": reverse(
                "manager:set-surface-permissions",
                kwargs={"pk": obj.id},
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
