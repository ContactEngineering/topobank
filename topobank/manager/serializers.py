import logging

import pint
from django.utils.translation import gettext_lazy as _
from guardian.shortcuts import get_users_with_perms
from rest_framework import serializers
from tagulous.contrib.drf import TagRelatedManagerField

from ..taskapp.serializers import TaskStateModelSerializer
from ..users.serializers import UserSerializer
from .models import FileManifest, FileParent, Property, Surface, Tag, Topography
from .utils import guardian_to_api

_log = logging.getLogger(__name__)
_ureg = pint.UnitRegistry()


# From: RomanKhudobei, https://github.com/encode/django-rest-framework/issues/1655
class StrictFieldMixin:
    """Raises error if read only fields or non-existing fields passed to input data"""

    default_error_messages = {
        "read_only": _("This field is read only"),
        "does_not_exist": _("This field does not exist"),
    }

    def to_internal_value(self, data):
        field_names = set(field.field_name for field in self._writable_fields)
        errors = {}

        # check that all dictionary keys are fields
        for key in data.keys():
            if key not in field_names:
                errors[key] = serializers.ErrorDetail(
                    self.error_messages["does_not_exist"], code="does_not_exist"
                )

        if errors != {}:
            raise serializers.ValidationError(errors)

        return super().to_internal_value(data)

    def validate(self, attrs):
        attrs = super().validate(attrs)

        if not hasattr(self, "initial_data"):
            return attrs

        # collect declared read only fields and read only fields from Meta
        read_only_fields = {
            field_name for field_name, field in self.fields.items() if field.read_only
        } | set(getattr(self.Meta, "read_only_fields", set()))

        received_read_only_fields = set(self.initial_data) & read_only_fields

        if received_read_only_fields:
            errors = {}
            for field_name in received_read_only_fields:
                errors[field_name] = serializers.ErrorDetail(
                    self.error_messages["read_only"], code="read_only"
                )

            raise serializers.ValidationError(errors)

        return attrs


class TagSerializer(StrictFieldMixin, serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Tag
        fields = ["url", "id", "name", "surfaces"]

    url = serializers.HyperlinkedIdentityField(
        view_name="manager:tag-api-detail", lookup_field="name", read_only=True
    )
    surfaces = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        optional_fields = [
            ("surfaces", "surfaces")
        ]
        for option, field in optional_fields:
            param = self.context["request"].query_params.get(option)
            requested = param is not None and param.lower() in ["yes", "true"]
            if not requested:
                self.fields.pop(field)

    def get_surfaces(self, obj):
        request = self.context["request"]
        obj.authenticate_user(request.user)
        return SurfaceSerializer(obj.related_surfaces(), context=self.context, many=True).data


class FileUploadSerializer(serializers.Serializer):
    surface = serializers.HyperlinkedRelatedField(view_name='manager:surface-api-detail',
                                                  queryset=Surface.objects.all(),
                                                  required=False)
    topography = serializers.HyperlinkedRelatedField(view_name='manager:topography-api-detail',
                                                     queryset=Topography.objects.all(),
                                                     required=False)
    kind = serializers.ChoiceField(choices=FileManifest.FILE_KIND_CHOICES)
    file_name = serializers.CharField()
    file_type = serializers.CharField(allow_blank=True)

    def validate(self, data):
        surface_value = data.get('surface')
        topography_value = data.get('topography')

        if surface_value is None and topography_value is None:
            raise serializers.ValidationError("Exactly one of surface or topography must be provided.")
        elif surface_value is not None and topography_value is not None:
            raise serializers.ValidationError("Only one of surface or topography should be provided, not both.")

        if surface_value is not None:
            data['parent'], _ = FileParent.objects.get_or_create(surface=surface_value)
            del data['surface']
        elif topography_value is not None:
            data['parent'], _ = FileParent.objects.get_or_create(topography=topography_value)
            del data['topography']

        return data


class FileManifestSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = FileManifest
        fields = ['url',
                  'file_name',
                  'file',
                  'kind',
                  'created',
                  'updated',
                  'creator_name',
                  ]

    url = serializers.HyperlinkedIdentityField(view_name='manager:file-api-detail', read_only=True)
    file = serializers.FileField(read_only=True)
    kind = serializers.ChoiceField(choices=FileManifest.FILE_KIND_CHOICES)
    created = serializers.DateTimeField(read_only=True)
    updated = serializers.DateTimeField(read_only=True)
    creator_name = serializers.SerializerMethodField()

    def get_creator_name(self, obj):
        return obj.uploaded_by.name


class TopographySerializer(StrictFieldMixin,
                           TaskStateModelSerializer):
    class Meta:
        model = Topography
        fields = ['url',
                  'id',
                  'surface',
                  'name',
                  'creator',
                  'datafile', 'datafile_format', 'channel_names', 'data_source',
                  'squeezed_datafile',
                  'description',
                  'measurement_date',
                  'size_editable', 'size_x', 'size_y',
                  'unit_editable', 'unit',
                  'height_scale_editable', 'height_scale',
                  'has_undefined_data', 'fill_undefined_data_mode',
                  'detrend_mode',
                  'resolution_x', 'resolution_y',
                  'bandwidth_lower', 'bandwidth_upper',
                  'short_reliability_cutoff',
                  'is_periodic_editable', 'is_periodic',
                  'instrument_name', 'instrument_type', 'instrument_parameters',
                  'upload_instructions',
                  'is_metadata_complete',
                  'thumbnail',
                  'creation_datetime', 'modification_datetime',
                  'duration', 'error', 'task_progress', 'task_state', 'tags',  # TaskStateModelSerializer
                  'attachments',
                  'permissions']

    url = serializers.HyperlinkedIdentityField(view_name='manager:topography-api-detail', read_only=True)
    creator = serializers.HyperlinkedRelatedField(view_name='users:user-api-detail', read_only=True)
    surface = serializers.HyperlinkedRelatedField(view_name='manager:surface-api-detail',
                                                  queryset=Surface.objects.all())

    attachments = FileManifestSerializer(many=True)

    tags = TagRelatedManagerField(required=False)

    is_metadata_complete = serializers.SerializerMethodField()

    upload_instructions = serializers.DictField(
        default=None, read_only=True
    )  # Pre-signed upload location

    permissions = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if 'request' not in self.context:
            return
        # We only return permissions and attachments if requested to do so
        optional_fields = ['permissions', 'attachments']
        for field in optional_fields:
            param = self.context['request'].query_params.get(field)
            requested = param is not None and param.lower() in ['yes', 'true']
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
        users = get_users_with_perms(obj.surface, attach_perms=True)
        return {
            "current_user": {
                "user": UserSerializer(current_user, context=self.context).data,
                "permission": guardian_to_api(users[current_user]),
            },
            "other_users": [
                {
                    "user": UserSerializer(key, context=self.context).data,
                    "permission": guardian_to_api(value),
                }
                for key, value in users.items()
                if key != current_user
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


class PropertySerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Property
        fields = ["url", "name", "value", "unit", "surface"]

    url = serializers.HyperlinkedIdentityField(
        view_name="manager:property-api-detail", read_only=True
    )
    name = serializers.CharField()
    value = ValueField()
    unit = serializers.CharField(allow_null=True, allow_blank=True, required=False)
    surface = serializers.HyperlinkedRelatedField(
        view_name="manager:surface-api-detail", queryset=Surface.objects.all()
    )

    def to_representation(self, instance):
        repr = super().to_representation(instance)
        if instance.is_numerical and instance.unit is None:
            repr["unit"] = ""
        return repr

    def validate_value(self, value):
        if not (
            isinstance(value, str) or isinstance(value, float) or isinstance(value, int)
        ):
            raise serializers.ValidationError(
                f"value must be of type float or string, but got {type(value)}"
            )
        return value

    def validate(self, attrs):
        if isinstance(attrs.get("value"), str) and attrs.get("unit") is not None:
            raise serializers.ValidationError(
                {
                    "message": "If the value is categorical (str), the unit has to be 'null'"
                }
            )
        if isinstance(attrs.get("value"), str) and attrs.get("value") == "":
            raise serializers.ValidationError(
                {"message": "This field may not be blank"}
            )
        if (
            isinstance(attrs.get("value"), int) or isinstance(attrs.get("value"), float)
        ) and attrs.get("unit") is None:
            raise serializers.ValidationError(
                {
                    "message": "If the value is categorical (int | float), the unit has to be not 'null' (str)"
                }
            )
        if not self.context["request"].user.has_perm(
            "change_surface", attrs.get("surface")
        ):
            raise serializers.ValidationError(
                {"message": "You do not have the permissions to change this surface"}
            )
        # If the peoperty changes from a numeric to categoric the unit needs to be 'None'
        # This ensures that the unit is set to None when its omitted
        if "unit" not in attrs:
            attrs["unit"] = None

        if attrs["unit"] is not None:
            try:
                _ureg.check(attrs["unit"])
            except pint.errors.UndefinedUnitError:
                unit = attrs["unit"]
                raise serializers.ValidationError(
                    {"message": f"Unit '{unit}' is not a physical unit"}
                )

        method = self.context.get("request").method
        # NOTE: On creation (POST) we need to check if the surface already has a property with the same name
        if method == "POST":
            if attrs.get("surface").properties.filter(name=attrs.get("name")).exists():
                raise serializers.ValidationError(
                    {"message": "Property names have to be unique"}
                )

        # NOTE: On update (PUT) we need to check if the surface already has a property with the same name,
        # that is not the surface we are trying to update
        if method == "PUT":
            if self.instance is None:
                # NOTE:This code should not be reachable.
                # On update, the serializer should always hold a instance
                pass
            else:
                if (
                    attrs.get("surface")
                    .properties.filter(name=attrs.get("name"))
                    .exclude(id=self.instance.id)
                    .exists()
                ):
                    raise serializers.ValidationError(
                        {"message": "Property names have to be unique"}
                    )
        return attrs


class SurfaceSerializer(StrictFieldMixin, serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Surface
        fields = ['url',
                  'id',
                  'name',
                  'category',
                  'creator',
                  'description',
                  'tags',
                  'creation_datetime', 'modification_datetime',
                  'topography_set',
                  'permissions',
                  'properties',
                  'attachments']

    url = serializers.HyperlinkedIdentityField(view_name='manager:surface-api-detail', read_only=True)
    creator = serializers.HyperlinkedRelatedField(view_name='users:user-api-detail', read_only=True)

    topography_set = TopographySerializer(many=True, read_only=True)
    properties = PropertySerializer(many=True)
    attachments = FileManifestSerializer(many=True)
    tags = TagRelatedManagerField(required=False)
    permissions = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        optional_fields = [
            ('children', 'topography_set'),
            ('permissions', 'permissions'),
            ('properties', 'properties'),
            ('attachments', 'attachments')
        ]
        for option, field in optional_fields:
            param = self.context["request"].query_params.get(option)
            requested = param is not None and param.lower() in ["yes", "true"]
            if not requested:
                self.fields.pop(field)

    def get_permissions(self, obj):
        request = self.context["request"]
        current_user = request.user
        users = get_users_with_perms(obj, attach_perms=True)
        return {
            "current_user": {
                "user": UserSerializer(current_user, context=self.context).data,
                "permission": (
                    guardian_to_api(users[current_user])
                    if current_user in users
                    else "no-access"
                ),
            },
            "other_users": [
                {
                    "user": UserSerializer(key, context=self.context).data,
                    "permission": guardian_to_api(value),
                }
                for key, value in users.items()
                if key != current_user
            ],
        }
