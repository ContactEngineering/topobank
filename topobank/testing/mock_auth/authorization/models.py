from django.conf import settings
from django.db import models


class PermissionSet(models.Model):
    name = models.CharField(max_length=255, default="")

    class Meta:
        app_label = 'mock_authorization'


class UserPermission(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    permission_set = models.ForeignKey(PermissionSet, on_delete=models.CASCADE)

    class Meta:
        app_label = 'mock_authorization'
