from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.reverse import reverse

from topobank.authorization.models import (
    OrganizationPermission,
    Permissions,
    PermissionSet,
    UserPermission,
)
from topobank.organizations.serializers import OrganizationSerializer
from topobank.supplib.serializers import UserField


class UserPermissionSerializer(serializers.ModelSerializer):
    """Serializer for user permissions"""

    class Meta:
        model = UserPermission
        fields = ("id", "user", "allow", "is_current_user")

    user = UserField(read_only=True)
    is_current_user = serializers.SerializerMethodField()

    def get_is_current_user(self, obj: UserPermission) -> bool:
        return self.context["request"].user == obj.user


class OrganizationPermissionSerializer(serializers.ModelSerializer):
    """Serializer for organization permissions"""

    class Meta:
        model = OrganizationPermission
        fields = ("id", "organization", "allow")

    organization = OrganizationSerializer(read_only=True)


class PermissionSetSerializer(serializers.ModelSerializer):
    """Serializer for permission sets"""

    class Meta:
        model = PermissionSet
        fields = ("id", "url", "user_permissions", "organization_permissions", "api")

    url = serializers.HyperlinkedIdentityField(
        view_name="authorization:permission-set-v2-detail", lookup_field="pk", read_only=True
    )
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
                "revoke_user_access",
                "grant_organization_access",
                "revoke_organization_access",
            ],
        }
    )
    def get_api(self, obj: PermissionSet) -> dict:
        request = self.context["request"]
        return {
            "grant_user_access": reverse(
                "authorization:grant-user-access-v2",
                kwargs={"id": obj.id},
                request=request,
            ),
            "revoke_user_access": reverse(
                "authorization:revoke-user-access-v2",
                kwargs={"id": obj.id},
                request=request,
            ),
            "grant_organization_access": reverse(
                "authorization:grant-organization-access-v2",
                kwargs={"id": obj.id},
                request=request,
            ),
            "revoke_organization_access": reverse(
                "authorization:revoke-organization-access-v2",
                kwargs={"id": obj.id},
                request=request,
            ),
        }


class SharedUserPermissionSerializer(serializers.Serializer):
    """Serializer for shared user permissions across multiple permission sets"""

    user = UserField(read_only=True)
    allow = serializers.ChoiceField(
        choices=[
            ("no-access", "No Access"),
            (Permissions.view.name, "View"),
            (Permissions.edit.name, "Edit"),
            (Permissions.full.name, "Full"),
        ],
        help_text="Effective permission level across all considered permission sets",
    )
    is_current_user = serializers.BooleanField()
    is_unique = serializers.BooleanField(
        help_text="True if the permission level is the same across all permission sets"
    )


class SharedOrganizationPermissionSerializer(serializers.Serializer):
    """Serializer for shared organization permissions across multiple permission sets"""

    organization = OrganizationSerializer(read_only=True)
    allow = serializers.ChoiceField(
        choices=[
            ('no-access', "No Access"),
            (Permissions.view.name, "View"),
            (Permissions.edit.name, "Edit"),
            (Permissions.full.name, "Full"),
        ],
        help_text="Effective permission level across all considered permission sets",
    )
    is_unique = serializers.BooleanField(
        help_text="True if the permission level is the same across all permission sets"
    )


class SharedPermissionSetSerializer(serializers.Serializer):
    """Serializer for shared permission sets"""

    user_permissions = SharedUserPermissionSerializer(many=True)
    organization_permissions = SharedOrganizationPermissionSerializer(
        many=True
    )


class GrantUserRequestSerializer(serializers.Serializer):
    """Serializer for granting user access request"""

    user = serializers.CharField(
        help_text="User identifier (URL or ID) to grant access to"
    )
    allow = serializers.ChoiceField(
        choices=[
            ("no-access", "No Access"),
            (Permissions.view.name, "View"),
            (Permissions.edit.name, "Edit"),
            (Permissions.full.name, "Full"),
        ],
        help_text="Permission level to grant",
    )


class RevokeUserRequestSerializer(serializers.Serializer):
    """Serializer for revoking user access request"""

    user = serializers.CharField(
        help_text="User identifier (URL or ID) to revoke access from"
    )


class GrantOrganizationRequestSerializer(serializers.Serializer):
    """Serializer for granting organization access request"""

    organization = serializers.CharField(
        help_text="Organization identifier (URL or ID) to grant access to"
    )
    allow = serializers.ChoiceField(
        choices=[
            ("no-access", "No Access"),
            (Permissions.view.name, "View"),
            (Permissions.edit.name, "Edit"),
            (Permissions.full.name, "Full"),
        ],
        help_text="Permission level to grant",
    )


class RevokeOrganizationRequestSerializer(serializers.Serializer):
    """Serializer for revoking organization access request"""

    organization = serializers.CharField(
        help_text="Organization identifier (URL or ID) to revoke access from"
    )
