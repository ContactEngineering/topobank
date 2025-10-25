import logging
from typing import Set
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models
from django.urls import resolve
from django.utils.translation import gettext_lazy as _
from rest_framework.reverse import reverse

_log = logging.getLogger(__name__)

DEFAULT_ORGANIZATION_NAME = "World"
DEFAULT_GROUP_NAME = "all"


class OrganizationManager(models.Manager):
    def for_user(self, user: settings.AUTH_USER_MODEL) -> models.QuerySet:
        """Return queryset with all organizations the given user belongs to."""
        return self.filter(group__in=user.groups.all())

    def get_plugins_available(self, user: settings.AUTH_USER_MODEL) -> Set[str]:
        """Return list with names of effective plugins available."""

        result = set()
        for pa in self.for_user(user).values_list("plugins_available"):
            result.update(x.strip() for x in pa[0].split(","))

        return result


class Organization(models.Model):
    """Represents an organization like a company or a scientific workgroup in a university."""

    name = models.CharField(_("Name of Organization"), max_length=255, unique=True)
    plugins_available = models.CharField(
        _("Available Plugins"),
        max_length=255,
        blank=True,
        help_text="""Comma-separated list of names of plugin packages
                                         available for this organization.
                                         """,
    )
    group = models.OneToOneField(
        Group,
        on_delete=models.CASCADE,  # delete organization with group
        help_text="Group which corresponds to members of this organization.",
    )

    objects = OrganizationManager()

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        """
        Called when saving this instance.

        Also ensures that a group with same name as the organization is
        created and linked to this instance.
        Exception: Organization "World" is linked to the group "all"
        By default, each new organization has no plugins.
        """
        if self.pk is None:
            # This is a new organization, we need to create a corresponding group
            group_name = self.name
            if group_name == DEFAULT_ORGANIZATION_NAME:
                group_name = DEFAULT_GROUP_NAME

            group, group_created = Group.objects.get_or_create(name=group_name)
            if group_created:
                _log.info(
                    f"Created group '{group_name}' for being associated with "
                    f"organization '{self.name}'."
                )
            self.group = group

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)

        # On deletion of an organization, the corresponding group should also be
        # deleted.
        _log.info(
            f"Deleting group '{self.group.name}' because of deletion of "
            f"organization '{self.name}'."
        )
        self.group.delete()

    def add(self, user: settings.AUTH_USER_MODEL):
        """Add user to this organization."""
        user.groups.add(self.group)

    def get_absolute_url(self, request=None):
        """URL of API endpoint for this organization"""
        return reverse("organizations:organization-v1-detail", kwargs={"pk": self.pk}, request=request)


def resolve_organization(url):
    try:
        id = int(url)
        return Organization.objects.get(pk=id)
    except ValueError:
        match = resolve(urlparse(url).path)
        if match.view_name != "organizations:organization-v1-detail":
            raise ValueError("URL does not resolve to an Organization instance")
        return Organization.objects.get(**match.kwargs)
