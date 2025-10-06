from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.reverse import reverse

from topobank.authorization.models import (
    OrganizationPermission,
    PermissionSet,
    UserPermission,
)


class UserStubSerializer(serializers.ModelSerializer):
    """Serializer for user stubs"""

    class Meta:
        model = UserPermission.user.field.related_model  # type: ignore
        fields = ("id", "username", "url")

    url = serializers.HyperlinkedIdentityField(view_name="users:user-v1-detail")


class OrganizationStubSerializer(serializers.ModelSerializer):
    """Serializer for organization stubs"""

    class Meta:
        model = OrganizationPermission.organization.field.related_model  # type: ignore
        fields = ("id", "name", "url")

    url = serializers.HyperlinkedIdentityField(view_name="organizations:organization-v1-detail")


class UserPermissionSerializer(serializers.ModelSerializer):
    """Serializer for user permissions"""

    class Meta:
        model = UserPermission
        fields = ("id", "user", "allow", "is_current_user")

    user = UserStubSerializer(read_only=True)
    is_current_user = serializers.SerializerMethodField()

    def get_is_current_user(self, obj: UserPermission) -> bool:
        return self.context['request'].user == obj.user


class OrganizationPermissionSerializer(serializers.ModelSerializer):
    """Serializer for organization permissions"""

    class Meta:
        model = OrganizationPermission
        fields = ("id", "organization", "allow")

    organization = OrganizationStubSerializer(read_only=True)


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
                "add_user": {"type": "string"},
                "remove_user": {"type": "string"},
                "add_organization": {"type": "string"},
                "remove_organization": {"type": "string"},
            },
            "required": ["add_user", "remove_user", "add_organization", "remove_organization"],
        }
    )
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
