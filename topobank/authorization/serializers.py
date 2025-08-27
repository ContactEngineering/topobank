from rest_framework import serializers

from topobank.authorization.models import (
    UserPermission,
    OrganizationPermission,
    PermissionSet,
)


class UserPermissionSerializer(serializers.ModelSerializer):
    """Serializer for user permissions"""

    class Meta:
        model = UserPermission
        fields = ("user_url", "allow", "is_current_user")

    user_url = serializers.HyperlinkedRelatedField(
        source="user", view_name="users:user-v1-detail", read_only=True
    )
    is_current_user = serializers.SerializerMethodField()

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
