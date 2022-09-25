from django.db import models
from django.contrib.auth.models import Group
from django.utils.translation import ugettext_lazy as _

from django.contrib.auth.models import Group


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

