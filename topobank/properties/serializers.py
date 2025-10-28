from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from topobank.properties.models import Property


class ValueField(serializers.Field):
    def to_representation(self, value):
        return value

    def to_internal_value(self, data):
        return data


@extend_schema_field(
    {
        "type": "object",
        "patternProperties": {
            "^.*$": {
                "type": "object",
                "properties": {
                    "value": {"anyOf": [{"type": "string"}, {"type": "number"}]},
                    "unit": {"type": "string"},
                },
                "required": ["value"],
            },
        },
        "additionalProperties": False,
    }
)
class PropertiesField(serializers.Field):
    def to_representation(self, value):
        ret = {}
        for prop in value.all():
            ret[prop.name] = {"value": prop.value}
            if prop.unit is not None:
                ret[prop.name]["unit"] = str(prop.unit)
        return ret

    def to_internal_value(self, data: dict[str, dict[str, str]]):
        surface = self.root.instance
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
