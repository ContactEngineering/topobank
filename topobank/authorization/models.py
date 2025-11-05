"""
Models related to authorization.
"""
import logging
from enum import Enum
from typing import Literal

from django.db import models
from django.db.models import Q, QuerySet
from notifications.signals import notify
from rest_framework.exceptions import NotFound, PermissionDenied

from ..organizations.models import Organization
from ..users.anonymous import get_anonymous_user
from ..users.models import User

_log = logging.getLogger(__name__)
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

        # Get user permissions
        user_permissions = self.user_permissions.filter(
            Q(user=user) | Q(user=anonymous_user)
        )
        nb_user_permissions = user_permissions.count()

        # Get organization permissions
        organization_permissions = self.organization_permissions.filter(
            organization__group__in=user.groups.all()
        )
        nb_organization_permissions = organization_permissions.count()

        # Idiot check
        if nb_user_permissions > 1:
            raise RuntimeError(
                f"More than one user permission found for user {user}. "
                "This should not happen."
            )

        # Get maximum access level
        max_access_level = 0
        if nb_user_permissions > 0:
            max_access_level = max(
                max_access_level,
                max(ACCESS_LEVELS[perm.allow] for perm in user_permissions),
            )
        if nb_organization_permissions > 0:
            max_access_level = max(
                max_access_level,
                max(ACCESS_LEVELS[perm.allow] for perm in organization_permissions),
            )
        if max_access_level == 0:
            return None
        else:
            return PERMISSION_CHOICES[max_access_level - 1][0]

    def grant_for_user(self, user: User, allow: ViewEditFull):
        """Grant permission to user"""
        existing_permissions = self.user_permissions.filter(user=user)
        nb_existing_permissions = existing_permissions.count()
        if nb_existing_permissions == 0:
            # Create new permission if none exists
            UserPermission.objects.create(parent=self, user=user, allow=allow)
        elif nb_existing_permissions == 1:
            # Update permission if it already exists
            (permission,) = existing_permissions
            permission.allow = allow
            permission.save(update_fields=["allow"])
        else:
            raise RuntimeError(
                f"More than one permission found for user {user}. "
                "This should not happen."
            )

    def revoke_from_user(self, user: User):
        """Revoke all permissions from user"""
        self.user_permissions.filter(user=user).delete()

    def grant_for_organization(self, organization: Organization, allow: ViewEditFull):
        """
        Grant permission to an organization (which means to all users from
        that organization)
        """
        existing_permissions = self.organization_permissions.filter(
            organization=organization
        )
        nb_existing_permissions = existing_permissions.count()
        if nb_existing_permissions == 0:
            # Create new permission if none exists
            OrganizationPermission.objects.create(
                parent=self, organization=organization, allow=allow
            )
        elif nb_existing_permissions == 1:
            # Update permission if it already exists
            (permission,) = existing_permissions
            permission.allow = allow
            permission.save(update_fields=["allow"])
        else:
            raise RuntimeError(
                f"More than one permission found for organization {organization}. "
                "This should not happen."
            )

    def revoke_from_organization(self, organization: Organization):
        """Revoke all permissions from an organization"""
        self.organization_permissions.filter(organization=organization).delete()

    def grant(self, user_or_organization: User | Organization, allow: ViewEditFull):
        """Grant permission"""
        if isinstance(user_or_organization, User):
            return self.grant_for_user(user_or_organization, allow)
        elif isinstance(user_or_organization, Organization):
            return self.grant_for_organization(user_or_organization, allow)
        else:
            raise TypeError("`user_or_organization` must be a User or an Organization")

    def revoke(self, user_or_organization: User | Organization):
        """Revoke permission"""
        if isinstance(user_or_organization, User):
            return self.revoke_from_user(user_or_organization)
        elif isinstance(user_or_organization, Organization):
            return self.revoke_from_organization(user_or_organization)
        else:
            raise TypeError("`user_or_organization` must be a User or an Organization")

    def user_has_permission(self, user: User, access_level: ViewEditFull) -> bool:
        """Check if user has permission for access level given by `allow`"""
        perm = self.get_for_user(user)
        if perm:
            return ACCESS_LEVELS[perm] >= ACCESS_LEVELS[access_level]
        else:
            return False

    def authorize_user(self, user: User, access_level: ViewEditFull):
        """
        Authorize user for access level given by `allow`. Raise
        `PermissionDenied` if user does not have sufficient access.
        Raise `NotFound` if user has no access at all.
        """
        perm = self.get_for_user(user)
        if perm is None:
            # User has no access at all, raise 404 to not leak information
            raise NotFound()
        elif ACCESS_LEVELS[perm] < ACCESS_LEVELS[access_level]:
            raise PermissionDenied(
                f"User '{user}' has permission '{perm}', cannot elevate to "
                f"permission '{access_level}'."
            )

    def notify_users(self, sender, verb, description):
        """Notify all users with permissions except sender"""
        # Exclude anonymous user in notifications
        anonymous_user = get_anonymous_user()
        for permission in self.user_permissions.exclude(
            Q(user=sender) | Q(user=anonymous_user)
        ):
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


class OrganizationPermission(models.Model):
    """Permission applying to all members of an organization"""

    class Meta:
        # There can only be one permission per organization
        unique_together = ("parent", "organization")

    # The set this permission belongs to
    parent = models.ForeignKey(
        PermissionSet, on_delete=models.CASCADE, related_name="organization_permissions"
    )

    # Organization that this permission relates to
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

    # The actual permission
    allow = models.CharField(max_length=4, choices=PERMISSION_CHOICES)


class AuthorizedQuerySet(QuerySet):
    """QuerySet with permission filtering capabilities."""
    def for_user(self, user: User, permission: ViewEditFull = "view") -> QuerySet:
        if permission == "view":
            # We do not need to filter on permission, just check that there
            # is some permission for the user
            return self.filter(
                # If anonymous has access, anybody can access
                Q(permissions__user_permissions__user=get_anonymous_user())
                # Direct user access
                | Q(permissions__user_permissions__user=user)
                # User access through an organization
                | Q(
                    permissions__organization_permissions__organization__group__in=user.groups.all()
                )
            )
        else:
            return self.filter(
                # Direct user access
                (
                    Q(permissions__user_permissions__user=user)
                    & Q(
                        permissions__user_permissions__allow__in=levels_with_access(
                            permission
                        )
                    )
                )
                # User access through an organization
                | (
                    Q(
                        permissions__organization_permissions__organization__group__in=user.groups.all()
                    )
                    & Q(
                        permissions__organization_permissions__allow__in=levels_with_access(
                            permission
                        )
                    )
                )
            )


class AuthorizedManager(models.Manager):
    def get_queryset(self) -> AuthorizedQuerySet:
        return AuthorizedQuerySet(self.model, using=self._db)

    def create(self, **kwargs):
        if "permissions" not in kwargs:
            # Create a new PermissionSet if one wasn't provided
            kwargs["permissions"] = PermissionSet.objects.create()
            _log.debug("AuthorizedManager created new PermissionSet for %s", self.model)
        if "folder" in [f.name for f in self.model._meta.get_fields()] and "folder" not in kwargs:
            # Import here to avoid circular import
            from topobank.files.models import Folder
            # Create a new PermissionSet for the folder as well
            kwargs["folder"] = Folder.objects.create(
                permissions=kwargs["permissions"],
                read_only=True,
            )
            _log.debug("AuthorizedManager created new Folder for %s", self.model)
        return super().create(**kwargs)

    def for_user(self, user: User, permission: ViewEditFull = "view") -> QuerySet:
        return self.get_queryset().for_user(user, permission)
