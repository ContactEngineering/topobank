from django.conf import settings
from django.db import models

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
        """Return all PermissionSets where user has at least the given permission level"""
        allowed_levels = levels_with_access(permission)
        return self.get_queryset().filter(
            user_permissions__user=user,
            user_permissions__allow__in=allowed_levels
        )


class PermissionSet(AbstractPermissionSet):
    name = models.CharField(max_length=255, default="")

    objects = PermissionSetManager()

    class Meta:
        app_label = 'authorization'

    @classmethod
    def filter_queryset(cls, queryset, user, permission):
        """Filter domain-object queryset to items accessible to user."""
        allowed_levels = levels_with_access(permission)
        return queryset.filter(
            permissions__user_permissions__user=user,
            permissions__user_permissions__allow__in=allowed_levels
        )

    def get_for_user(self, user):
        """Return permissions of a specific user"""
        user_permissions = list(self.user_permissions.filter(user=user))
        nb_user_permissions = len(user_permissions)
        if nb_user_permissions > 1:
            raise RuntimeError(
                f"More than one user permission found for {user}. "
                "This should not happen."
            )
        if nb_user_permissions == 0:
            return None
        return user_permissions[0].allow

    def grant_for_user(self, user, allow: ViewEditFull):
        """Grant permission to user"""
        UserPermission.objects.update_or_create(
            parent=self, user=user,
            defaults={"allow": allow},
        )

    def revoke_from_user(self, user):
        """Revoke all permissions from user"""
        self.user_permissions.filter(user=user).delete()

    def grant(self, principal, allow: ViewEditFull):
        """Grant permission"""
        return self.grant_for_user(principal, allow)

    def revoke(self, principal):
        """Revoke permission"""
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
