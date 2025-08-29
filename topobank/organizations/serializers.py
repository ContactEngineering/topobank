from drf_spectacular.utils import extend_schema_field
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
            "api",
            # Model fields
            "name",
            "plugins_available",
        ]

    url = serializers.HyperlinkedIdentityField(
        view_name="organizations:organization-v1-detail", read_only=True
    )
    api = serializers.SerializerMethodField()

    @extend_schema_field(
        {
            "type": "object",
            "properties": {
                "users": {"type": "string"},
                "add_user": {"type": "string"},
                "remove_user": {"type": "string"},
            },
        }
    )
    def get_api(self, obj: Organization) -> dict:
        request = self.context["request"]
        return {
            "users": reverse("users:user-v1-list", request=request)
            + f"?organization={obj.id}",
            "add_user": reverse(
                "organizations:add-user-v1",
                kwargs={"pk": obj.id},
                request=request,
            ),
            "remove_user": reverse(
                "organizations:remove-user-v1",
                kwargs={"pk": obj.id},
                request=request,
            ),
        }
