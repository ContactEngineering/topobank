from urllib.parse import urlparse

from django.urls import resolve
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.reverse import reverse


# From: RomanKhudobei, https://github.com/encode/django-rest-framework/issues/1655
class StrictFieldMixin:
    """
    Raises error if read-only fields or non-existing fields are passed as input data
    """

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
        read_only_fields = {field_name for field_name, field in self.fields.items() if field.read_only} | set(
            getattr(self.Meta, "read_only_fields", set()))

        received_read_only_fields = set(self.initial_data) & read_only_fields

        if received_read_only_fields:
            errors = {}
            for field_name in received_read_only_fields:
                errors[field_name] = serializers.ErrorDetail(
                    self.error_messages["read_only"], code="read_only"
                )

            raise serializers.ValidationError(errors)

        return attrs


# https://www.django-rest-framework.org/api-guide/serializers/#example
class DynamicFieldsModelSerializer(serializers.ModelSerializer):
    """
    A ModelSerializer that takes an additional `fields` argument that
    controls which fields should be displayed.
    """

    def __init__(self, *args, **kwargs):
        # Instantiate the superclass normally
        super(DynamicFieldsModelSerializer, self).__init__(*args, **kwargs)

        fields = self.context["request"].query_params.get("fields")
        exclude = self.context["request"].query_params.get("exclude")
        if exclude:
            exclude = exclude.split(",")
            # Drop any fields that are specified in the `exclude` argument.
            for field_name in exclude:
                if field_name in self.fields:
                    self.fields.pop(field_name)
        if fields:
            fields = fields.split(",")
            # Drop any fields that are not specified in the `fields` argument.
            allowed = set(fields)
            existing = set(self.fields.keys())
            for field_name in existing - allowed:
                self.fields.pop(field_name)


@extend_schema_field(
    {
        "type": "object",
        "properties": {
            "id": {"type": "number"},
            "url": {"type": "string"},
            "allow": {"enum": ["view", "edit", "full"]},
        },
        "required": ["id", "url", "allow"],
    }
)
class PermissionsField(serializers.RelatedField):
    """
    A reusable Django REST Framework related field that returns a dictionary
    containing both the object's identifier and a hyperlinked URL.

    The serialized representation takes the form:

        {
            "id": <object id>,
            "url": <hyperlinked URL>
            "allow": <permissions of current user>
        }

    Parameters
    ----------
    view_name : str, optional
        The name of the DRF view used to generate the hyperlink.
        Must correspond to a valid URL pattern name in the project.
        (Default: 'authorization:permission-set-v2-detail')
    lookup_field : str, optional
        The name of the model field used for URL lookup.
        (Default: 'pk')
    **kwargs
        Additional keyword arguments passed to the parent `Field` class.
    """

    def __init__(
        self,
        view_name="authorization:permission-set-v2-detail",
        lookup_field="pk",
        **kwargs,
    ):
        self.view_name = view_name
        self.lookup_field = lookup_field
        super().__init__(**kwargs)

    def to_representation(self, obj):
        """
        Convert the model instance into a dictionary containing
        both the object's ID and its hyperlinked URL.

        Parameters
        ----------
        obj : Model instance
            The model instance being serialized.

        Returns
        -------
        dict
            A dictionary with the following structure:
            {
                "id": <object id>,
                "url": <hyperlinked URL>
                "allow": <permissions of current user>
            }
        """
        request = self.context.get("request", None)
        lookup_value = getattr(obj, self.lookup_field, None)

        url = None
        if lookup_value is not None and self.view_name:
            url = reverse(
                self.view_name,
                kwargs={self.lookup_field: lookup_value},
                request=request,
            )

        return {"id": lookup_value, "url": url, "allow": obj.get_for_user(request.user)}


@extend_schema_field(
    {
        "type": "object",
        "properties": {
            "id": {"type": "number"},
            "url": {"type": "string"},
        },
    }
)
class ModelRelatedField(serializers.RelatedField):
    """
    A reusable Django REST Framework related field that returns a dictionary
    representation of an object with ID, URL, and optionally additional fields.

    Parameters
    ----------
    view_name : str
        The name of the DRF view used to generate the hyperlink.
        Must correspond to a valid URL pattern name in the project.
    lookup_field : str, optional
        The name of the model field used for URL lookup.
        (Default: 'pk')
    fields : list of str, optional
        A list of additional model fields to include in the serialized output.
        (Default: None)
    """

    default_error_messages = {
        'id_url_not_present': _('Either "id" or "url" must be present in the input data.')
    }

    def __init__(
        self,
        view_name,
        lookup_field="pk",
        fields=None,
        **kwargs,
    ):
        self.view_name = view_name
        self.lookup_field = lookup_field
        self.fields = fields
        super().__init__(**kwargs)

    def to_representation(self, obj):
        """
        Convert the model instance into a dictionary.

        Parameters
        ----------
        obj : Model instance
            The model instance being serialized.

        Returns
        -------
        dict
            A dictionary representation of the model instance.
            {
                "id": <object id>,
                "url": <hyperlinked URL>,
                "<field1>": <value1>,
                "<field2>": <value2>,
                ...
            }
        """
        data = {
            "id": obj.pk,
            "url": reverse(
                self.view_name,
                kwargs={self.lookup_field: getattr(obj, self.lookup_field)},
                request=self.context.get("request", None),
            )
        }
        if self.fields:
            for field in self.fields:
                data[field] = getattr(obj, field)
        return data

    def to_internal_value(self, data):
        """
        Convert the input data back into a model instance.

        Parameters
        ----------
        data : dict
            The input data containing at least the 'id' of the model instance.

        Returns
        -------
        Model instance
            The corresponding model instance.
        """
        id = data.get("id", None)
        url = data.get("url", None)
        if id is None and url is not None:
            match = resolve(urlparse(url=url).path)
            if match.view_name != self.view_name:
                self.fail('incorrect_match')
            return self.get_queryset().get(**match.kwargs)
        elif id is not None:
            return self.get_queryset().get(id=id)
        else:
            self.fail('id_url_not_present')


@extend_schema_field(
    {
        "type": "object",
        "properties": {
            "id": {"type": "number"},
            "url": {"type": "string"},
            "name": {"type": "string"},
        },
        "required": ["id", "url", "name"],
    }
)
class UserField(ModelRelatedField):
    """
    A reusable Django REST Framework related field that returns a dictionary
    containing the user's identifier, a hyperlinked URL, and name.

    The serialized representation takes the form:

        {
            "id": <user id>,
            "url": <hyperlinked URL>,
            "name": <user_name>
        }
    """

    def __init__(self, **kwargs):
        super().__init__(view_name="users:user-v1-detail",
                         lookup_field="pk",
                         fields=["name"],
                         **kwargs)


class OrganizationField(ModelRelatedField):
    """
    A reusable Django REST Framework related field that returns a dictionary
    containing the organization's identifier, a hyperlinked URL, and name.

    The serialized representation takes the form:

        {
            "id": <organization id>,
            "url": <hyperlinked URL>,
            "name": <organization_name>
        }
    """

    def __init__(self, **kwargs):
        super().__init__(view_name="organizations:organization-v1-detail",
                         lookup_field="pk",
                         fields=["name"],
                         **kwargs)
