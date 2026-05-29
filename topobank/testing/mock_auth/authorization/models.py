from django.conf import settings
from django.db import models
from django.db.models import Q

from topobank.authorization.models import (
    ACCESS_LEVELS,
    PERMISSION_CHOICES,
    AbstractPermissionSet,
    ViewEditFull,
    ViewEditFullNone,
    levels_with_access,
)


class PermissionSetManager(models.Manager):
    def create(self, user=None, allow: ViewEditFullNone = None, **kwargs):
        if user is not None or allow is not None:
            if user is None or allow is None:
                raise RuntimeError(
                    "You need to provide both user and permission when creating a "
                    "PermissionSet."
                )
            permission_set = super().create(**kwargs)
            permission_set.grant_for_user(user, allow)
            return permission_set
        else:
            return super().create(**kwargs)

    def for_user(self, user, permission: ViewEditFull = "view"):
        """Return all PermissionSets where user has at least the given permission level.

        For `view`, also matches sets where the anonymous user has the
        permission — authenticated users inherit anonymous view access
        when one is configured.
        """
        from topobank.authorization import get_anonymous_user
        allowed_levels = levels_with_access(permission)
        anonymous_user = (
            get_anonymous_user() if permission == "view" else None
        )
        if anonymous_user is not None:
            return self.get_queryset().filter(
                Q(user_permissions__user=user,
                  user_permissions__allow__in=allowed_levels)
                | Q(user_permissions__user=anonymous_user,
                    user_permissions__allow__in=allowed_levels)
            ).distinct()
        return self.get_queryset().filter(
            user_permissions__user=user,
            user_permissions__allow__in=allowed_levels,
        )


class PermissionSet(AbstractPermissionSet):
    name = models.CharField(max_length=255, default="")

    objects = PermissionSetManager()

    class Meta:
        app_label = 'authorization'

    @classmethod
    def filter_queryset(cls, queryset, user, permission):
        """Filter domain-object queryset to items accessible to user.

        For `view`, also includes items where the anonymous user has the
        permission — authenticated users inherit anonymous view access
        when one is configured.
        """
        from topobank.authorization import get_anonymous_user
        allowed_levels = levels_with_access(permission)
        anonymous_user = (
            get_anonymous_user() if permission == "view" else None
        )
        if anonymous_user is not None:
            return queryset.filter(
                Q(permissions__user_permissions__user=user,
                  permissions__user_permissions__allow__in=allowed_levels)
                | Q(permissions__user_permissions__user=anonymous_user,
                    permissions__user_permissions__allow__in=allowed_levels)
            ).distinct()
        return queryset.filter(
            permissions__user_permissions__user=user,
            permissions__user_permissions__allow__in=allowed_levels,
        )

    def get_for_user(self, user):
        """Return the effective permission for a user.

        Falls back to the anonymous user's permission when the user has no
        explicit row and an anonymous user is configured — authenticated
        users inherit anonymous access.
        """
        from topobank.authorization import get_anonymous_user
        anonymous_user = get_anonymous_user()
        if anonymous_user is None:
            user_permissions = list(self.user_permissions.filter(user=user))
        else:
            user_permissions = list(self.user_permissions.filter(
                Q(user=user) | Q(user=anonymous_user)
            ))
        if not user_permissions:
            return None
        max_access_level = max(
            ACCESS_LEVELS[perm.allow] for perm in user_permissions
        )
        if max_access_level == 0:
            return None
        return PERMISSION_CHOICES[max_access_level - 1][0]

    def grant_for_user(self, user, allow: ViewEditFull):
        """Grant permission to user"""
        UserPermission.objects.update_or_create(
            parent=self, user=user,
            defaults={"allow": allow},
        )

    def revoke_from_user(self, user):
        """Revoke all permissions from user"""
        self.user_permissions.filter(user=user).delete()

    def grant_for_organization(self, organization, allow: ViewEditFull):
        """Grant permission to an organization"""
        OrganizationPermission.objects.update_or_create(
            parent=self, organization=organization,
            defaults={"allow": allow},
        )

    def revoke_from_organization(self, organization):
        """Revoke all permissions from an organization"""
        self.organization_permissions.filter(organization=organization).delete()

    def grant(self, principal, allow: ViewEditFull):
        """Grant permission"""
        from topobank.testing.mock_auth.organizations.models import Organization
        if isinstance(principal, Organization):
            return self.grant_for_organization(principal, allow)
        return self.grant_for_user(principal, allow)

    def revoke(self, principal):
        """Revoke permission"""
        from topobank.testing.mock_auth.organizations.models import Organization
        if isinstance(principal, Organization):
            return self.revoke_from_organization(principal)
        return self.revoke_from_user(principal)

    def user_has_permission(self, user, access_level: ViewEditFull) -> bool:
        """Check if user has permission for access level given by `allow`"""
        perm = self.get_for_user(user)
        if perm:
            return ACCESS_LEVELS[perm] >= ACCESS_LEVELS[access_level]
        else:
            return False

    def authorize_user(self, user, access_level: ViewEditFull):
        """Authorize user; raise PermissionDenied or NotFound if insufficient."""
        from django.core.exceptions import PermissionDenied
        from django.http import Http404 as NotFound

        perm = self.get_for_user(user)
        if perm is None:
            raise NotFound()
        elif ACCESS_LEVELS[perm] < ACCESS_LEVELS[access_level]:
            raise PermissionDenied(
                f"User '{user}' has permission '{perm}', cannot elevate to "
                f"permission '{access_level}'."
            )

    def notify_users(self, sender, verb, description):
        """Notify all users with permissions except sender"""
        pass  # No-op for mock

    def get_users(self):
        """Return all users with their permissions"""
        return [(perm.user, perm.allow) for perm in self.user_permissions.all()]


class UserPermission(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    parent = models.ForeignKey(
        PermissionSet,
        on_delete=models.CASCADE,
        related_name="user_permissions"
    )
    allow = models.CharField(max_length=10, default="view", choices=PERMISSION_CHOICES)

    class Meta:
        app_label = 'authorization'
        unique_together = ("parent", "user")


class OrganizationPermission(models.Model):
    """Permission applying to all members of an organization"""
    parent = models.ForeignKey(
        PermissionSet,
        on_delete=models.CASCADE,
        related_name="organization_permissions"
    )
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE
    )
    allow = models.CharField(max_length=4, choices=PERMISSION_CHOICES)

    class Meta:
        app_label = 'authorization'
        unique_together = ("parent", "organization")
