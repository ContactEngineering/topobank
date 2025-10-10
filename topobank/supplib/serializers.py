from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


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


# https://www.django-rest-framework.org/api-guide/serializers/#example
class DynamicFieldsModelSerializer(serializers.ModelSerializer):
    """
    A ModelSerializer that takes an additional `fields` argument that
    controls which fields should be displayed.
    """

    def __init__(self, *args, **kwargs):
        # Instantiate the superclass normally
        super(DynamicFieldsModelSerializer, self).__init__(*args, **kwargs)

        fields = self.context['request'].query_params.get('fields')
        exclude = self.context['request'].query_params.get('exclude')
        if exclude:
            exclude = exclude.split(',')
            # Drop any fields that are specified in the `exclude` argument.
            for field_name in exclude:
                if field_name in self.fields:
                    self.fields.pop(field_name)
        if fields:
            fields = fields.split(',')
            # Drop any fields that are not specified in the `fields` argument.
            allowed = set(fields)
            existing = set(self.fields.keys())
            for field_name in existing - allowed:
                self.fields.pop(field_name)
