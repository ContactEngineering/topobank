from rest_framework import serializers
from rest_framework.reverse import reverse

from ..supplib.serializers import StrictFieldMixin
from .models import Organization


class OrganizationSerializer(StrictFieldMixin, serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Organization
        fields = [
            # Self
            "url",
            "id",
            # Auxiliary API endpoints
            'api',
            # Model fields
            "name",
            "plugins_available"
        ]

    url = serializers.HyperlinkedIdentityField(
        view_name="organizations:organization-v1-detail", read_only=True
    )
    api = serializers.SerializerMethodField()

    def get_api(self, obj: Organization) -> dict:
        return {
            "add_user": reverse(
                "organizations:add-user-v1",
                kwargs={"pk": obj.id},
                request=self.context["request"],
            ),
            "remove_user": reverse(
                "organizations:remove-user-v1",
                kwargs={"pk": obj.id},
                request=self.context["request"],
            )
        }
