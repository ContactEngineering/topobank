"""
Abstract authorization models.

Concrete implementations (PermissionSet, UserPermission, OrganizationPermission)
live in topobank.testing.mock_auth.
"""
from enum import Enum
from typing import Literal

from django.db import models
from django.db.models import QuerySet


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

# Integers for access levels for comparisons in authorization
ACCESS_LEVELS = {None: 0, **{p.name: p.value for p in Permissions}}

VIEW = Permissions.view.name
EDIT = Permissions.edit.name
FULL = Permissions.full.name

ViewEditFull = Literal[
    Permissions.view.name, Permissions.edit.name, Permissions.full.name
]
ViewEditFullNone = ViewEditFull | None


def levels_with_access(perm: ViewEditFull) -> set:
    retval = set()
    for i in range(ACCESS_LEVELS[perm], len(PERMISSION_CHOICES) + 1):
        retval.add(PERMISSION_CHOICES[i - 1][0])
    return retval


class AbstractPermissionSet(models.Model):
    """Contract all concrete permission implementations must satisfy."""

    @classmethod
    def filter_queryset(cls, queryset, user, permission):
        """Filter domain-object queryset to items accessible to user."""
        raise NotImplementedError

    def get_for_user(self, user):
        raise NotImplementedError

    def grant(self, principal, allow):
        raise NotImplementedError

    def revoke(self, principal):
        raise NotImplementedError

    def user_has_permission(self, user, access_level) -> bool:
        raise NotImplementedError

    def authorize_user(self, user, access_level):
        raise NotImplementedError

    def get_users(self) -> list:
        raise NotImplementedError

    def notify_users(self, sender, verb, description):
        raise NotImplementedError

    class Meta:
        abstract = True


class AuthorizedQuerySet(QuerySet):
    """QuerySet with permission filtering capabilities."""
    def for_user(self, user, permission: ViewEditFull = "view") -> QuerySet:
        from topobank.authorization import get_permission_model
        return get_permission_model().filter_queryset(self, user, permission)


class AuthorizedManager(models.Manager):
    def get_queryset(self) -> AuthorizedQuerySet:
        return AuthorizedQuerySet(self.model, using=self._db)

    def create(self, **kwargs):
        return super().create(**kwargs)

    def for_user(self, user, permission: ViewEditFull = "view") -> QuerySet:
        return self.get_queryset().for_user(user, permission)


class SurfaceTopographyManager(AuthorizedManager):
    """Default manager for Surface and Topography that excludes soft-deleted records."""

    def get_queryset(self) -> AuthorizedQuerySet:
        return super().get_queryset().filter(deletion_time__isnull=True)
