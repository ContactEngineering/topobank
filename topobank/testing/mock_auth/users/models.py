from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    orcid_id = models.CharField(max_length=19, default="0000-0000-0000-0000")
    name = models.CharField("Name of User", blank=True, max_length=255, default="")

    class Meta:
        app_label = 'mock_users'
