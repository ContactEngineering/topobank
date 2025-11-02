"""
Custom Django REST Framework serializers and fields for the topobank application.

This module provides reusable serializer components that extend Django REST Framework
functionality with common patterns used throughout the application:

- StrictFieldMixin: Enforces strict validation of input fields
- DynamicFieldsModelSerializer: Enables dynamic field selection via query parameters
- PermissionsField: Serializes objects with permission information
- ModelRelatedField: Generic field for serializing related objects with URLs
- UserField: Specialized field for user objects
- OrganizationField: Specialized field for organization objects

These components help maintain consistency across API endpoints and provide enhanced
validation and flexibility for API consumers.
"""
from urllib.parse import urlparse

from django.urls import resolve
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.reverse import reverse


# From: RomanKhudobei, https://github.com/encode/django-rest-framework/issues/1655
class StrictFieldMixin:
    """
    A mixin that enforces strict field validation for Django REST Framework serializers.

    This mixin provides two levels of validation:
    1. Ensures that only fields defined in the serializer are accepted in input data
    2. Prevents read-only fields from being included in input data

    By default, DRF silently ignores unknown fields and read-only fields in input data.
    This mixin makes the API more explicit by raising validation errors when clients
    attempt to provide invalid fields, helping catch bugs and improve API clarity.

    Usage
    -----
    Mix this class into your serializer before the base serializer class::

        class MySerializer(StrictFieldMixin, serializers.ModelSerializer):
            class Meta:
                model = MyModel
                fields = ['id', 'name', 'description']
                read_only_fields = ['id']

    Examples
    --------
    With the above serializer, these requests would raise validation errors:

    - Invalid field: ``{"name": "Test", "invalid_field": "value"}``
      Error: ``{"invalid_field": "This field does not exist"}``

    - Read-only field: ``{"id": 123, "name": "Test"}``
      Error: ``{"id": "This field is read only"}``

    Notes
    -----
    Credit: RomanKhudobei
    Source: https://github.com/encode/django-rest-framework/issues/1655
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
    A ModelSerializer that allows clients to dynamically control which fields are returned.

    This serializer enables API clients to customize the response payload by specifying
    which fields to include or exclude via query parameters. This is useful for:
    - Reducing payload size by excluding unnecessary fields
    - Optimizing mobile or bandwidth-constrained applications
    - Creating flexible APIs that support multiple use cases

    Query Parameters
    ----------------
    fields : str, optional
        Comma-separated list of field names to include in the response.
        Only the specified fields will be returned.
        Example: ``?fields=id,name,created_at``

    exclude : str, optional
        Comma-separated list of field names to exclude from the response.
        All fields except the specified ones will be returned.
        Example: ``?exclude=description,metadata``

    Usage
    -----
    Use this as a base class instead of `serializers.ModelSerializer`::

        class MySerializer(DynamicFieldsModelSerializer):
            class Meta:
                model = MyModel
                fields = ['id', 'name', 'description', 'created_at', 'updated_at']

    Examples
    --------
    Given a serializer with fields: ``['id', 'name', 'description', 'created_at']``

    - Request only specific fields:
      ``GET /api/items/?fields=id,name``
      Returns only ``id`` and ``name`` fields

    - Exclude specific fields:
      ``GET /api/items/?exclude=description``
      Returns all fields except ``description``

    - If neither parameter is provided:
      ``GET /api/items/``
      Returns all fields defined in the serializer

    Notes
    -----
    - The ``fields`` and ``exclude`` parameters cannot be used together
    - Invalid field names in the query parameters are silently ignored
    - This serializer requires a request context to function properly

    See Also
    --------
    Source: https://www.django-rest-framework.org/api-guide/serializers/#example
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
    A specialized Django REST Framework field for serializing permission sets.

    This field extends the standard related field to include permission information
    for the current user alongside the object's ID and URL. This is particularly
    useful for frontend applications that need to determine what actions the current
    user is allowed to perform on related objects.

    The serialized representation takes the form::

        {
            "id": <object id>,
            "url": <hyperlinked URL>,
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

    Usage
    -----
    Include this field in your serializer to represent related permission sets::

        class DatasetSerializer(serializers.ModelSerializer):
            permissions = PermissionsField(read_only=True)

            class Meta:
                model = Dataset
                fields = ['id', 'name', 'permissions']

    Examples
    --------
    For a user with 'edit' permissions on a permission set with ID 42::

        {
            "id": 42,
            "url": "https://example.com/api/permissions/42/",
            "allow": "edit"
        }

    The 'allow' field typically contains one of: "view", "edit", or "full"

    Notes
    -----
    - The related object must implement a ``get_for_user(user)`` method that returns
      the permission level for the given user
    - This field requires a request context to determine the current user
    - This field is typically read-only as permissions are managed separately
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
    A versatile Django REST Framework field for serializing related model instances.

    This field provides a flexible way to represent related objects as dictionaries
    containing their ID, a hyperlinked URL to their detail endpoint, and optionally
    any additional fields from the model. This is more informative than a simple
    primary key representation while being lighter weight than a full nested serializer.

    The field also supports deserialization, accepting either an ID or a URL to
    identify the related object.

    Parameters
    ----------
    view_name : str
        The name of the DRF view used to generate the hyperlink.
        Must correspond to a valid URL pattern name in the project.
        Example: 'api:dataset-detail'
    lookup_field : str, optional
        The name of the model field used for URL lookup.
        (Default: 'pk')
    fields : list of str, optional
        A list of additional model fields to include in the serialized output.
        These fields will be read directly from the model instance.
        (Default: None)
    **kwargs
        Additional keyword arguments passed to the parent `RelatedField` class.

    Usage
    -----
    Use this field to represent related objects with ID and URL::

        class ArticleSerializer(serializers.ModelSerializer):
            author = ModelRelatedField(
                view_name='api:author-detail',
                queryset=Author.objects.all(),
                read_only=False
            )

            class Meta:
                model = Article
                fields = ['id', 'title', 'author']

    To include additional fields from the related model::

        class ArticleSerializer(serializers.ModelSerializer):
            author = ModelRelatedField(
                view_name='api:author-detail',
                fields=['name', 'email'],
                queryset=Author.objects.all()
            )

            class Meta:
                model = Article
                fields = ['id', 'title', 'author']

    Examples
    --------
    Output with basic configuration (no additional fields)::

        {
            "id": 1,
            "title": "My Article",
            "author": {
                "id": 42,
                "url": "https://example.com/api/authors/42/"
            }
        }

    Output with additional fields::

        {
            "id": 1,
            "title": "My Article",
            "author": {
                "id": 42,
                "url": "https://example.com/api/authors/42/",
                "name": "John Doe",
                "email": "john@example.com"
            }
        }

    Input for deserialization (ID-based)::

        {
            "title": "New Article",
            "author": {"id": 42}
        }

    Input for deserialization (URL-based)::

        {
            "title": "New Article",
            "author": {"url": "https://example.com/api/authors/42/"}
        }

    Notes
    -----
    - When deserializing, either 'id' or 'url' must be provided in the input data
    - If a URL is provided for deserialization, it will be resolved to verify it
      matches the expected view_name
    - Additional fields specified in the 'fields' parameter are only used for
      serialization (output), not deserialization (input)
    - This field requires a request context to generate URLs
    """

    default_error_messages = {
        'id_url_both_present': _('"id" and "url" are both present, please provide only one.'),
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
        elif id is not None and url is None:
            return self.get_queryset().get(id=id)
        elif id is None and url is None:
            self.fail('id_url_not_present')
        else:
            self.fail('id_url_both_present')


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
    A specialized field for representing User model instances in API responses.

    This field is a pre-configured version of ModelRelatedField specifically designed
    for user objects. It automatically includes the user's name along with their ID
    and a hyperlink to their detail endpoint.

    The serialized representation takes the form::

        {
            "id": <user id>,
            "url": <hyperlinked URL>,
            "name": <user_name>
        }

    Parameters
    ----------
    **kwargs
        Additional keyword arguments passed to ModelRelatedField.
        Common options include 'queryset' and 'read_only'.

    Usage
    -----
    Use this field whenever you need to represent a user relationship::

        class CommentSerializer(serializers.ModelSerializer):
            author = UserField(read_only=True)
            last_edited_by = UserField(
                queryset=User.objects.all(),
                required=False,
                allow_null=True
            )

            class Meta:
                model = Comment
                fields = ['id', 'text', 'author', 'last_edited_by']

    Examples
    --------
    Serialized output::

        {
            "id": 123,
            "text": "Great article!",
            "author": {
                "id": 42,
                "url": "https://example.com/api/users/42/",
                "name": "Jane Smith"
            }
        }

    Input for deserialization::

        {
            "text": "Updated comment",
            "last_edited_by": {"id": 42}
        }

    Notes
    -----
    - This field is pre-configured to use the 'users:user-v1-detail' view name
    - The 'name' field is automatically included from the User model
    - For read-only fields representing the current user, consider using
      `UserField(read_only=True, default=serializers.CurrentUserDefault())`
    """

    def __init__(self, **kwargs):
        super().__init__(view_name="users:user-v1-detail",
                         lookup_field="pk",
                         fields=["name"],
                         **kwargs)


class OrganizationField(ModelRelatedField):
    """
    A specialized field for representing Organization model instances in API responses.

    This field is a pre-configured version of ModelRelatedField specifically designed
    for organization objects. It automatically includes the organization's name along
    with its ID and a hyperlink to its detail endpoint.

    The serialized representation takes the form::

        {
            "id": <organization id>,
            "url": <hyperlinked URL>,
            "name": <organization_name>
        }

    Parameters
    ----------
    **kwargs
        Additional keyword arguments passed to ModelRelatedField.
        Common options include 'queryset' and 'read_only'.

    Usage
    -----
    Use this field whenever you need to represent an organization relationship::

        class ProjectSerializer(serializers.ModelSerializer):
            owner_organization = OrganizationField(
                queryset=Organization.objects.all(),
                required=True
            )
            collaborating_organizations = OrganizationField(
                many=True,
                queryset=Organization.objects.all(),
                required=False
            )

            class Meta:
                model = Project
                fields = ['id', 'name', 'owner_organization', 'collaborating_organizations']

    Examples
    --------
    Serialized output for a single organization::

        {
            "id": 10,
            "name": "Research Project",
            "owner_organization": {
                "id": 5,
                "url": "https://example.com/api/organizations/5/",
                "name": "Acme Research Labs"
            }
        }

    Serialized output with multiple organizations::

        {
            "id": 10,
            "name": "Joint Research Project",
            "collaborating_organizations": [
                {
                    "id": 5,
                    "url": "https://example.com/api/organizations/5/",
                    "name": "Acme Research Labs"
                },
                {
                    "id": 7,
                    "url": "https://example.com/api/organizations/7/",
                    "name": "University Science Dept"
                }
            ]
        }

    Input for deserialization::

        {
            "name": "New Project",
            "owner_organization": {"id": 5}
        }

    Notes
    -----
    - This field is pre-configured to use the 'organizations:organization-v1-detail' view name
    - The 'name' field is automatically included from the Organization model
    - Use `many=True` when the field represents a many-to-many relationship
    """

    def __init__(self, **kwargs):
        super().__init__(view_name="organizations:organization-v1-detail",
                         lookup_field="pk",
                         fields=["name"],
                         **kwargs)
