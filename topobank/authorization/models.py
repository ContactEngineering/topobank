"""
Models related to authorization.
"""

from enum import Enum
from typing import Literal

from django.db import models
from django.db.models import Q, QuerySet
from notifications.signals import notify
from rest_framework.exceptions import PermissionDenied

from ..users.anonymous import get_anonymous_user
from ..users.models import User


# The types of permissions
class Permissions(Enum):
    view = 1
    edit = 2
    full = 3


# Choices for database field
PERMISSION_CHOICES = [
    (Permissions.view.name, "Read-only access"),
    (Permissions.edit.name, "Change the model data"),
    (Permissions.full.name, "Grant/revoke permissions of other users"),
]

# Integers for access levels for comparisons in authorization:
# Access is granted if the access level is higher or equal to the
# requested level
ACCESS_LEVELS = {None: 0, **{p.name: p.value for p in Permissions}}

ViewEditFull = Literal[
    Permissions.view.name, Permissions.edit.name, Permissions.full.name
]
ViewEditFullNone = ViewEditFull | None


def levels_with_access(perm: ViewEditFull) -> set:
    retval = set()
    for i in range(ACCESS_LEVELS[perm], len(PERMISSION_CHOICES) + 1):
        retval.add(PERMISSION_CHOICES[i - 1][0])
    return retval


class PermissionSetManager(models.Manager):
    def create(self, user: User = None, allow: ViewEditFullNone = None, **kwargs):
        if user is not None or allow is not None:
            if user is None or allow is None:
                raise RuntimeError(
                    "You need to provide both user and permission when creating a "
                    "PermissionSet."
                )
            # Create a new PermissionSet
            permission_set = super().create(**kwargs)
            # Grant the permission to the user
            permission_set.grant_for_user(user, allow)
            return permission_set
        else:
            # Create a new PermissionSet without any permissions
            return super().create(**kwargs)


class PermissionSet(models.Model):
    """A set of permissions"""

    # Currently we only have per-user permissions, but it is foreseeable that
    # we will have per-organization permissions at some point in the
    # future.

    # The following reverse relations exist
    # permissions: Actual permission(s), per user

    #
    # Manager
    #
    objects = PermissionSetManager()

    def get_for_user(self, user: User):
        """Return permissions of a specific user"""
        anonymous_user = get_anonymous_user()
        permissions = self.user_permissions.filter(
            Q(user=user) | Q(user=anonymous_user)
        )
        nb_permissions = len(permissions)
        if len(permissions) > 2:
            raise RuntimeError(
                f"More than one permission found for user {user}. "
                "This should not happen."
            )
        elif nb_permissions > 0:
            max_access_level = max(ACCESS_LEVELS[perm.allow] for perm in permissions)
            return PERMISSION_CHOICES[max_access_level - 1][0]
        else:
            return None

    def grant_for_user(self, user: User, allow: ViewEditFull):
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
            permission.save()
        else:
            raise RuntimeError(
                f"More than one permission found for user {user}. "
                "This should not happen."
            )

    def revoke_from_user(self, user: User):
        """Revoke all permissions from user"""
        self.user_permissions.filter(user=user).delete()

    def user_has_permission(self, user: User, access_level: ViewEditFull) -> bool:
        """Check if user has permission for access level given by `allow`"""
        perm = self.get_for_user(user)
        if perm:
            return ACCESS_LEVELS[perm] >= ACCESS_LEVELS[access_level]
        else:
            return False

    def authorize_user(self, user: User, access_level: ViewEditFull):
        """Authorize user for access level given by `allow`"""
        perm = self.get_for_user(user)
        if perm is None:
            raise PermissionDenied(
                f"User '{user}' has no access permission, cannot elevate to permission "
                f"'{access_level}'."
            )
        elif ACCESS_LEVELS[perm] < ACCESS_LEVELS[access_level]:
            raise PermissionDenied(
                f"User '{user}' has permission '{perm}', cannot elevate to "
                f"permission '{access_level}'."
            )

    def notify_users(self, sender, verb, description):
        for permission in self.user_permissions.exclude(user=sender):
            notify.send(
                sender=sender,
                recipient=permission.user,
                verb=verb,
                description=description,
            )

    def get_users(self):
        """Return all users with their permissions"""
        return [(perm.user, perm.allow) for perm in self.user_permissions.all()]


class UserPermission(models.Model):
    """Single permission for a specific user"""

    class Meta:
        # There can only be one permission per user
        unique_together = ("parent", "user")

    # The set this permission belongs to
    parent = models.ForeignKey(
        PermissionSet, on_delete=models.CASCADE, related_name="user_permissions"
    )

    # User that this permission relates to
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    # The actual permission
    allow = models.CharField(max_length=4, choices=PERMISSION_CHOICES)


class AuthorizedManager(models.Manager):
    def create(self, **kwargs):
        # FIXME! Make sure that all objects have permission sets attached to them
        # if "permissions" not in kwargs:
        #    raise RuntimeError(
        #        "You need to provide permissions when creating an object."
        #    )
        return super().create(**kwargs)

    def for_user(self, user: User, permission: ViewEditFull = "view") -> QuerySet:
        if permission == "view":
            # We do not need to filter on permission
            return self.get_queryset().filter(
                Q(permissions__user_permissions__user=user)
                | Q(permissions__user_permissions__user=get_anonymous_user())
            )
        else:
            return self.get_queryset().filter(
                permissions__user_permissions__user=user,
                permissions__user_permissions__allow__in=levels_with_access(permission),
            )
