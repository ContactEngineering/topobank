from django.db import models

DEFAULT_GROUP_NAME = "default"
DEFAULT_ORGANIZATION_NAME = "default"


class Organization(models.Model):
    name = models.CharField(max_length=255, default="")

    class Meta:
        app_label = 'mock_organizations'
