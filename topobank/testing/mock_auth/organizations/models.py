import logging

from django.contrib.auth.models import Group
from django.db import models

_log = logging.getLogger(__name__)

DEFAULT_GROUP_NAME = "all"
DEFAULT_ORGANIZATION_NAME = "World"


class OrganizationManager(models.Manager):
    def for_user(self, user) -> models.QuerySet:
        """Return queryset with all organizations the given user belongs to."""
        return self.filter(group__in=user.groups.all())


class Organization(models.Model):
    name = models.CharField(max_length=255, default="")
    group = models.OneToOneField(
        Group,
        on_delete=models.CASCADE,
        null=True,
        help_text="Group which corresponds to members of this organization.",
    )

    objects = OrganizationManager()

    class Meta:
        app_label = 'organizations'

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if self.pk is None:
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
        group = self.group
        super().delete(*args, **kwargs)

        if group:
            _log.info(
                f"Deleting group '{group.name}' because of deletion of "
                f"organization '{self.name}'."
            )
            group.delete()

    def add(self, user):
        """Add user to this organization."""
        if self.group:
            user.groups.add(self.group)
