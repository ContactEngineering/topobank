import logging
from typing import Set
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.urls import resolve
from django.utils.translation import gettext_lazy as _
from rest_framework.reverse import reverse

_log = logging.getLogger(__name__)

DEFAULT_ORGANIZATION_NAME = "World"
DEFAULT_GROUP_NAME = "all"


def get_plugin_choices():
    """
    Get list of valid plugin choices from installed plugins.

    Returns a list of tuples (plugin_name, plugin_name) suitable for Django choices.
    Dynamically discovers plugins via entry points.
    """

    return [(name, name)
            for name in getattr(settings, 'PLUGIN_MODULES', [])
            if name not in getattr(settings, 'EXCLUDED_PLUGIN_CHOICES', [])
            ]


class OrganizationManager(models.Manager):
    def for_user(self, user: settings.AUTH_USER_MODEL) -> models.QuerySet:
        """Return queryset with all organizations the given user belongs to."""
        return self.filter(group__in=user.groups.all())

    def get_plugins_available(self, user: settings.AUTH_USER_MODEL) -> Set[str]:
        """Return list with names of effective plugins available."""

        result = set()
        for pa in self.for_user(user).values_list("plugins_available", flat=True):
            if pa:  # Skip empty lists
                result.update(pa)

        return result


class Organization(models.Model):
    """Represents an organization like a company or a scientific workgroup in a university."""

    name = models.CharField(_("Name of Organization"), max_length=255, unique=True)
    plugins_available = ArrayField(
        models.CharField(max_length=100, choices=get_plugin_choices),
        blank=True,
        default=list,
        verbose_name=_("Available Plugins"),
        help_text=_("Select from available plugin packages for this organization."),
    )
    group = models.OneToOneField(
        Group,
        on_delete=models.CASCADE,  # delete organization with group
        help_text="Group which corresponds to members of this organization.",
    )

    objects = OrganizationManager()

    def __str__(self) -> str:
        return self.name

    def clean(self):
        """Validate that all plugin names are valid installed plugins."""
        from django.core.exceptions import ValidationError

        super().clean()

        valid_plugins = set(getattr(settings, 'PLUGIN_MODULES', []))
        invalid_plugins = set(self.plugins_available) - valid_plugins

        if invalid_plugins:
            raise ValidationError({
                'plugins_available': _(
                    f"Invalid plugin names: {', '.join(sorted(invalid_plugins))}. "
                    f"Available plugins: {', '.join(sorted(valid_plugins))}"
                )
            })

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
