from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.reverse import reverse

from topobank.authorization.models import (
    OrganizationPermission,
    PermissionSet,
    UserPermission,
)


class UserPermissionSerializer(serializers.ModelSerializer):
    """Serializer for user permissions"""

    class Meta:
        model = UserPermission
        fields = ("url", "user_url", "allow", "is_current_user")

    url = serializers.HyperlinkedIdentityField(
        view_name="authorization:permission-set-v1-detail", read_only=True
    )
    user_url = serializers.HyperlinkedRelatedField(
        source="user", view_name="users:user-v1-detail", read_only=True
    )
    is_current_user = serializers.SerializerMethodField()
    api = serializers.SerializerMethodField()

    def get_is_current_user(self, obj: UserPermission) -> bool:
        return self.context["request"].user == obj.user


class OrganizationPermissionSerializer(serializers.ModelSerializer):
    """Serializer for organization permissions"""

    class Meta:
        model = OrganizationPermission
        fields = ("organization_url", "allow")

    organization_url = serializers.HyperlinkedRelatedField(
        source="organization",
        view_name="organizations:organization-v1-detail",
        read_only=True,
    )


class PermissionSetSerializer(serializers.ModelSerializer):
    """Serializer for permission sets"""

    class Meta:
        model = PermissionSet
        fields = ("user_permissions", "organization_permissions", "api")

    user_permissions = UserPermissionSerializer(many=True, read_only=True)
    organization_permissions = OrganizationPermissionSerializer(
        many=True, read_only=True
    )
    api = serializers.SerializerMethodField()

    @extend_schema_field(
        {
            "type": "object",
            "properties": {
                "grant_user_access": {"type": "string"},
                "revoke_user_access": {"type": "string"},
                "grant_organization_access": {"type": "string"},
                "revoke_organization_access": {"type": "string"},
            },
            "required": [
                "grant_user_access",
                "remove_userrevoke_user_access",
                "grant_organization_access",
                "revoke_organization_access",
            ],
        }
    )
    def get_api(self, obj: PermissionSet) -> dict:
        request = self.context["request"]
        return {
            "grant_user_access": reverse(
                "authorization:grant-user-v1",
                kwargs={"pk": obj.id},
                request=request,
            ),
            "revoke_user_access": reverse(
                "authorization:revoke-user-v1",
                kwargs={"pk": obj.id},
                request=request,
            ),
            "grant_organization_access": reverse(
                "authorization:grant-organization-v1",
                kwargs={"pk": obj.id},
                request=request,
            ),
            "revoke_organization_access": reverse(
                "authorization:revoke-organization-v1",
                kwargs={"pk": obj.id},
                request=request,
            ),
        }
