from allauth.account.utils import has_verified_email
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.reverse import reverse

from ..supplib.mixins import StrictFieldMixin
from .models import ORCIDException, User


class UserSerializer(StrictFieldMixin, serializers.HyperlinkedModelSerializer):
    """Serializer for User model."""
    class Meta:
        model = User
        fields = [
            # Self
            "url",
            "id",
            # Auxiliary API endpoints
            "api",
            # Model fields
            "name",
            "username",
            "orcid",
            "email",
            "date_joined",
            # Auth fields
            "is_verified",
        ]
        read_only_fields = ["id", "date_joined", "is_verified"]

    url = serializers.HyperlinkedIdentityField(
        view_name="users:user-v1-detail", read_only=True
    )
    api = serializers.SerializerMethodField()
    orcid = serializers.SerializerMethodField()
    is_verified = serializers.SerializerMethodField()

    @extend_schema_field(
        {
            "type": "object",
            "properties": {
                "organizations": {"type": "string", "readOnly": True},
                "add_organization": {"type": "string", "readOnly": True},
                "remove_organization": {"type": "string", "readOnly": True},
            },
            "required": ["organizations", "add_organization", "remove_organization"],
        }
    )
    def get_api(self, obj: User) -> dict:
        request = self.context["request"]
        return {
            "organizations": reverse(
                "organizations:organization-v1-list", request=request
            )
            + f"?user={obj.id}",
            "add_organization": reverse(
                "users:add-organization-v1",
                kwargs={"pk": obj.id},
                request=request,
            ),
            "remove_organization": reverse(
                "users:remove-organization-v1",
                kwargs={"pk": obj.id},
                request=request,
            ),
        }

    def get_orcid(self, obj: User) -> str:
        try:
            return obj.orcid_id
        except ORCIDException:
            return None

    def get_is_verified(self, obj: User) -> bool:
        return has_verified_email(obj)
