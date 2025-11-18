"""DRF View Mixins for common functionality."""


from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from topobank.organizations.models import Organization

######################
# Serializer Mixins  #
######################


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


################
# View Mixins  #
################


class UserUpdateMixin:
    """Mixin that tracks which user created and updated objects.

    Automatically sets created_by and updated_by fields based on the
    authenticated user making the request.

    Usage:
        class MyViewSet(UserUpdateMixin, viewsets.ModelViewSet):
            # Your view implementation
            pass
    """

    def perform_create(self, serializer):
        """Set created_by and updated_by when creating objects."""
        # Can't call super() here because we need to pass kwargs to save()
        user = self.request.user
        owned_by = Organization.objects.for_user(user).first()  # TODO: Limit to one organization per user
        serializer.save(owned_by=owned_by, created_by=user, updated_by=user)

    def perform_update(self, serializer):
        """Set updated_by when updating objects."""
        # Set the field on the instance then call super() to maintain MRO chain
        serializer.instance.updated_by = self.request.user
        super().perform_update(serializer)
