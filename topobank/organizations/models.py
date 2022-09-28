from django.db import models
from django.contrib.auth.models import Group
from django.utils.translation import ugettext_lazy as _

from django.contrib.auth.models import Group

import logging
_log = logging.getLogger(__name__)

DEFAULT_ORGANIZATION_NAME = "World"
DEFAULT_PLUGINS_AVAILABLE = "topobank_statistics, topobank_contact"
DEFAULT_GROUP_NAME = "all"


class OrganizationManager(models.Manager):
    def for_user(self, user):
        """Return queryset with all organizations the given user belongs to."""
        return self.filter(group__in=user.groups.all())

    def get_plugins_available(self, user):
        """Return list with names of effective plugins available."""

        result = set()
        for pa in self.for_user(user).values_list('plugins_available'):
            result.update(x.strip() for x in pa[0].split(','))

        return result


class Organization(models.Model):
    """Represents an organization like a company or a scientific workgroup in a university."""
    name = models.CharField(_("Name of Organization"), max_length=255)
    plugins_available = models.CharField(_("Available Plugins"),
                                         max_length=255,
                                         blank=True,
                                         help_text="""Comma-separated list of names of plugin packages
                                         available for this organization.
                                         """)
    group = models.OneToOneField(Group, on_delete=models.CASCADE,  # delete organization with group
                                 help_text="Group which corresponds to members of this organization.")

    objects = OrganizationManager()

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Called when saving this instance.

        Also ensures that a group with same
        name as the organization is created and
        linked to this instance.
        Exception: Organization "World" is linked to the
                   group "all"
        By default, each new organization gets the default plugins.
        """
        created = self.pk is None
        if created:
            group_name = self.name
            if group_name == DEFAULT_ORGANIZATION_NAME:
                group_name = DEFAULT_GROUP_NAME

            group, group_created = Group.objects.get_or_create(name=group_name)
            if group_created:
                _log.info(f"Created group '{group_name}' for being associated with organization '{self.name}'.")
            self.group = group

            if self.plugins_available == '':
                self.plugins_available = DEFAULT_PLUGINS_AVAILABLE

        super().save(*args, **kwargs)

