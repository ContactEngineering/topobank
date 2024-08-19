"""
Models related to authorization.
"""

from django.db import models
from jedi import InternalError

from ..users.models import User

# The types of permissions
PERMISSION_CHOICES = [
    ("read", "Read-only access"),
    ("edit", "Change the model data"),
    ("full", "Grant/revoke permissions of other users"),
]

# Integers for access levels for comparisons in authorization:
# Access is granted if the access level is higher or equal to the
# requested level
ACCESS_LEVELS = {
    None: 0,
    PERMISSION_CHOICES[0][1]: 1,
    PERMISSION_CHOICES[1][1]: 2,
    PERMISSION_CHOICES[2][1]: 3,
}


class PermissionSet(models.Model):
    """A set of permissions"""

    # Currently we only have per-user permissions, but it is foreseeable that
    # we will have per-organization permissions at some point in the
    # future.

    # The following reverse relations exist
    # permissions: Actual permission(s), per user

    def get_for_user(self, user):
        """Return permissions of a specific user"""
        permissions = self.user_permissions.filter(user=user)
        nb_permissions = len(permissions)
        if nb_permissions == 0:
            return None
        elif nb_permissions == 1:
            return permissions.first()
        else:
            raise InternalError(
                f"More than one permission found for user {user}. "
                "This should not happen."
            )

    def grant_for_user(self, user, allow):
        """Grant permission to user"""
        existing_permissions = self.user_permissions.filter(user=user)
        nb_existing_permissions = len(existing_permissions)
        if nb_existing_permissions == 0:
            # Create new permission if none exists
            UserPermission.objects.create(parent=self, user=user, allow=allow)
        elif nb_existing_permissions == 1:
            # Update permission if it already exists
            (permission,) = existing_permissions
            permission.allow = allow
        else:
            raise InternalError(
                f"More than one permission found for user {user}. "
                "This should not happen."
            )

    def revoke_from_user(self, user):
        """Revoke all permissions from user"""
        self.user_permissions.filter(user=user).delete()

    def authorize_user(self, user, allow):
        """Authorize user for access level given by `allow`"""
        perm = self.get_for_user(user)
        if ACCESS_LEVELS[perm] < ACCESS_LEVELS[allow]:
            raise PermissionError(
                f"User {user} has permission '{perm}', cannot elevate to permission "
                f"'{allow}'."
            )


class UserPermission(models.Model):
    """Single permission for a specific user"""

    class Meta:
        # There can only be one permission per user
        unique_together = ("user", "allow")

    # The set this permission belongs to
    parent = models.ForeignKey(
        PermissionSet, on_delete=models.CASCADE, related_name="user_permissions"
    )

    # User that this permission relates to
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    # The actual permission
    allow = models.CharField(max_length=4, choices=PERMISSION_CHOICES)
