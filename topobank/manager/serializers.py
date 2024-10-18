import logging

from django.db.models.deletion import transaction
from rest_framework import serializers
from rest_framework.reverse import reverse
from tagulous.contrib.drf import TagRelatedManagerField

from topobank.properties.models import Property

from ..files.serializers import ManifestSerializer
from ..supplib.serializers import StrictFieldMixin
from ..taskapp.serializers import TaskStateModelSerializer
from ..users.serializers import UserSerializer
from .models import Surface, Tag, Topography

_log = logging.getLogger(__name__)


class TagSerializer(StrictFieldMixin, serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Tag
        fields = [
            "url",
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
    children = serializers.SerializerMethodField()

    def get_children(self, obj: Tag):
        request = self.context["request"]
        obj.authorize_user(request.user, "view")
        return obj.get_children()


class TopographySerializer(StrictFieldMixin, TaskStateModelSerializer):
    class Meta:
        model = Topography
        fields = [
            "url",
            "id",
            "surface",
            "name",
            "creator",
            "datafile",
            "datafile_format",
            "channel_names",
            "data_source",
            "squeezed_datafile",
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
            "thumbnail",
            "creation_datetime",
            "modification_datetime",
            "duration",
            "error",
            "task_progress",
            "task_state",
            "tags",  # TaskStateModelSerializer
            "attachments",
            "permissions",
            "deepzoom",
        ]

    url = serializers.HyperlinkedIdentityField(
        view_name="manager:topography-api-detail", read_only=True
    )
    creator = serializers.HyperlinkedRelatedField(
        view_name="users:user-api-detail", read_only=True
    )
    surface = serializers.HyperlinkedRelatedField(
        view_name="manager:surface-api-detail", queryset=Surface.objects.all()
    )

    datafile = ManifestSerializer(required=False)
    squeezed_datafile = ManifestSerializer(required=False)
    thumbnail = ManifestSerializer(required=False)

    tags = TagRelatedManagerField(required=False)

    is_metadata_complete = serializers.SerializerMethodField()

    permissions = serializers.SerializerMethodField()
    deepzoom = serializers.HyperlinkedRelatedField(
        view_name="files:folder-api-detail", read_only=True
    )
    attachments = serializers.HyperlinkedRelatedField(
        view_name="files:folder-api-detail", read_only=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "request" not in self.context:
            return
        # We only return permissions if requested to do so
        optional_fields = ["permissions"]
        for field in optional_fields:
            param = self.context["request"].query_params.get(field)
            requested = param is not None and param.lower() in ["yes", "true"]
            if not requested:
                self.fields.pop(field)

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

    def get_is_metadata_complete(self, obj):
        return obj.is_metadata_complete

    def get_permissions(self, obj):
        request = self.context["request"]
        current_user = request.user
        user_permissions = obj.permissions.user_permissions.all()
        return {
            "current_user": {
                "user": UserSerializer(current_user, context=self.context).data,
                "permission": obj.get_permission(current_user),
            },
            "other_users": [
                {
                    "user": UserSerializer(perm.user, context=self.context).data,
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
        return super().update(instance, validated_data)


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
        with transaction.atomic():  # NOTE: This is probably not needed because django wraps views in a transaction.
            # WARNING: with the current API design surfaces can only be created with no properties.
            if surface is not None:
                surface.properties.all().delete()
                for property in data:
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
            "url",
            "id",
            "name",
            "category",
            "creator",
            "description",
            "tags",
            "creation_datetime",
            "modification_datetime",
            "topography_set",
            "permissions",
            "properties",
            "attachments",
            "topographies",
        ]

    url = serializers.HyperlinkedIdentityField(
        view_name="manager:surface-api-detail", read_only=True
    )
    creator = serializers.HyperlinkedRelatedField(
        view_name="users:user-api-detail", read_only=True
    )

    topography_set = TopographySerializer(many=True, read_only=True)
    properties = PropertiesField(required=False)
    tags = TagRelatedManagerField(required=False)
    permissions = serializers.SerializerMethodField()
    attachments = serializers.HyperlinkedRelatedField(
        view_name="files:folder-api-detail", read_only=True
    )
    topographies = serializers.SerializerMethodField()

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

    def get_permissions(self, obj):
        request = self.context["request"]
        current_user = request.user
        user_permissions = obj.permissions.user_permissions.all()
        return {
            "current_user": {
                "user": UserSerializer(current_user, context=self.context).data,
                "permission": obj.get_permission(current_user),
            },
            "other_users": [
                {
                    "user": UserSerializer(perm.user, context=self.context).data,
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
