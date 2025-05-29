from rest_framework import serializers

from ..supplib.serializers import StrictFieldMixin
from .models import Organization


class OrganizationSerializer(StrictFieldMixin, serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Organization
        fields = ["url", "id", "name", "plugins_available"]

    url = serializers.HyperlinkedIdentityField(
        view_name="organizations:organization-api-detail", read_only=True
    )
