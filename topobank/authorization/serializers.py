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
        fields = ("user_url", "api", "allow", "is_current_user")

    user_url = serializers.HyperlinkedRelatedField(
        source="user", view_name="users:user-v1-detail", read_only=True
    )
    api = serializers.SerializerMethodField()
    is_current_user = serializers.SerializerMethodField()

    def get_api(self, obj: PermissionSet) -> dict:
        request = self.context["request"]
        return {
            "add_user": reverse(
                "authorization:add-user-v1",
                kwargs={"pk": obj.id},
                request=request,
            ),
            "remove_user": reverse(
                "authorization:remove-user-v1",
                kwargs={"pk": obj.id},
                request=request,
            ),
            "add_organization": reverse(
                "authorization:add-organization-v1",
                kwargs={"pk": obj.id},
                request=request,
            ),
            "remove_organization": reverse(
                "authorization:remove-organization-v1",
                kwargs={"pk": obj.id},
                request=request,
            ),
        }

    def get_is_current_user(self, obj):
        return self.request.user == obj.user


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
        fields = ("user_permissions", "organization_permissions")

    user_permissions = UserPermissionSerializer(many=True, read_only=True)
    organization_permissions = OrganizationPermissionSerializer(
        many=True, read_only=True
    )
