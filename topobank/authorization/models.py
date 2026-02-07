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


def _filter_for_user(
    queryset: QuerySet,
    user: User,
    permission: ViewEditFull,
    prefix: str = ""
) -> QuerySet:
    """
    Shared implementation for filtering querysets by user permission.

    Args:
        queryset: The queryset to filter
        user: The user to check permissions for
        permission: The permission level to check
        prefix: Field prefix for permission lookups (e.g., "permissions__" or "")

    Note: This implementation uses UNION queries to optimize performance
    when filtering permissions, avoiding expensive OR conditions.
    Union queries come with some limitations (e.g., no further filtering after union),
    so we materialize IDs and return a regular filtered queryset at the end.
    """
    # Cache user groups to prevent query re-evaluation and improve query plan stability
    if not hasattr(user, '_cached_group_ids'):
        user._cached_group_ids = list(user.groups.values_list('id', flat=True))
    user_group_ids = user._cached_group_ids

    # Build field names with prefix
    user_perm_user = f"{prefix}user_permissions__user"
    user_perm_allow = f"{prefix}user_permissions__allow__in"
    org_perm_group = f"{prefix}organization_permissions__organization__group_id__in"
    org_perm_allow = f"{prefix}organization_permissions__allow__in"

    if permission == "view":
        # Use UNION instead of OR for better query performance
        # Each branch can use its own optimal index

        # Branch 1: Anonymous user can view
        qs_anonymous = queryset.filter(**{user_perm_user: get_anonymous_user()})

        # Branch 2: Direct user permission
        qs_user = queryset.filter(**{user_perm_user: user})

        # Branch 3: Organization permission (only if user belongs to groups)
        if user_group_ids:
            qs_org = queryset.filter(**{org_perm_group: user_group_ids})
            # UNION all three branches
            union_qs = qs_anonymous.union(qs_user, qs_org)
        else:
            # User not in any groups - skip org branch
            union_qs = qs_anonymous.union(qs_user)

        # Materialize IDs from UNION and return a regular filtered queryset
        # This allows further filtering/chaining while keeping UNION performance benefits
        accessible_ids = list(union_qs.values_list('id', flat=True))
        return queryset.filter(id__in=accessible_ids)
    else:
        # For edit/full permissions, check permission levels
        # No anonymous access for these permission levels
        allowed_levels = levels_with_access(permission)

        # Branch 1: Direct user permission with level check
        qs_user = queryset.filter(**{user_perm_user: user, user_perm_allow: allowed_levels})

        # Branch 2: Organization permission with level check (only if user belongs to groups)
        if user_group_ids:
            qs_org = queryset.filter(
                **{org_perm_group: user_group_ids, org_perm_allow: allowed_levels}
            )
            # UNION both branches
            union_qs = qs_user.union(qs_org)
        else:
            # User not in any groups - return only user branch (already filterable)
            return qs_user

        # Materialize IDs from UNION and return a regular filtered queryset
        accessible_ids = list(union_qs.values_list('id', flat=True))
        return queryset.filter(id__in=accessible_ids)


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

    def for_user(self, user: User, permission: ViewEditFull = "view") -> QuerySet:
        """Return all PermissionSets where user has at least the given permission level"""
        return _filter_for_user(self, user, permission, prefix="")


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

        # Check if user_permissions data is prefetched
        if 'user_permissions' in getattr(self, '_prefetched_objects_cache', {}):
            # Use prefetched data (no query)
            user_permissions = [
                p for p in self.user_permissions.all()
                if p.user == user or p.user == anonymous_user
            ]
        else:
            # Fall back to query
            user_permissions = list(self.user_permissions.filter(
                Q(user=user) | Q(user=anonymous_user)
            ))

        nb_user_permissions = len(user_permissions)

        # Cache user groups on user object to prevent re-evaluation
        if not hasattr(user, '_cached_group_ids'):
            user._cached_group_ids = list(user.groups.values_list('id', flat=True))
        user_group_ids = user._cached_group_ids

        # Check if organization_permissions data is prefetched
        if 'organization_permissions' in getattr(self, '_prefetched_objects_cache', {}):
            # Use prefetched data (no query)
            organization_permissions = [
                p for p in self.organization_permissions.all()
                if p.organization.group_id in user_group_ids
            ]
        else:
            # Fall back to query
            organization_permissions = list(self.organization_permissions.filter(
                organization__group_id__in=user_group_ids
            ))

        nb_organization_permissions = len(organization_permissions)

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
        indexes = [
            # Composite index for permission lookups by user and parent
            # Used in: get_for_user() queries
            models.Index(fields=['user', 'parent'], name='userperm_user_parent_idx'),
            # Index on parent for reverse lookups from PermissionSet
            # Used in: permission_set.user_permissions.all()
            models.Index(fields=['parent'], name='userperm_parent_idx'),
        ]

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
        indexes = [
            # Composite index for permission lookups by organization and parent
            # Used in: get_for_user() organization permission queries
            models.Index(fields=['organization', 'parent'], name='orgperm_org_parent_idx'),
            # Index on parent for reverse lookups from PermissionSet
            # Used in: permission_set.organization_permissions.all()
            models.Index(fields=['parent'], name='orgperm_parent_idx'),
        ]

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
        return _filter_for_user(self, user, permission, prefix="permissions__")


class AuthorizedManager(models.Manager):
    def get_queryset(self) -> AuthorizedQuerySet:
        return AuthorizedQuerySet(self.model, using=self._db)

    def create(self, **kwargs):
        return super().create(**kwargs)

    def for_user(self, user: User, permission: ViewEditFull = "view") -> QuerySet:
        return self.get_queryset().for_user(user, permission)
