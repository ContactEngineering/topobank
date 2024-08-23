"""
Basic models for the web app for handling topography data.
"""

import logging

from django.conf import settings
from django.db import models

from ..authorization.mixins import PermissionMixin
from ..authorization.models import AuthorizedManager, PermissionSet
from .utils import generate_upload_path

_log = logging.getLogger(__name__)


class Folder(PermissionMixin, models.Model):
    #
    # Manager
    #
    objects = AuthorizedManager()

    #
    # Permissions
    #
    permissions = models.ForeignKey(PermissionSet, on_delete=models.CASCADE, null=True)

    def get_valid_files(self) -> models.QuerySet["Manifest"]:
        # NOTE: "files" is the reverse `related_name` for the relation to `FileManifest`
        return self.files.filter(upload_finished__isnull=False)

    def __str__(self) -> str:
        return "Folder"


# The Flow for "direct file upload" is heavily inspired from here:
# https://www.hacksoft.io/blog/direct-to-s3-file-upload-with-django
class Manifest(PermissionMixin, models.Model):
    #
    # Manager
    #
    objects = AuthorizedManager()

    #
    # Permissions
    #
    permissions = models.ForeignKey(PermissionSet, on_delete=models.CASCADE, null=True)

    FILE_KIND_CHOICES = [("att", "Attachment"), ("raw", "Raw data file")]

    file = models.FileField(upload_to=generate_upload_path, blank=True, null=True)

    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=255, blank=True, null=True)

    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    # Folder can be null, in which case this is a single file that belongs to some
    # model (e.g. a raw data file or a thumbnail of a measurement)
    folder = models.ForeignKey(
        Folder, related_name="files", on_delete=models.CASCADE, null=True
    )
    kind = models.CharField(max_length=3, choices=FILE_KIND_CHOICES)

    upload_finished = models.DateTimeField(blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"FileManifest:\n\tfile -> {self.file}\n\tfolder -> {self.folder}\n\tkind -> {self.kind}"

    def delete(self, *args, **kwargs):
        self.file.delete(save=False)
        return super().delete(*args, **kwargs)

    @property
    def is_valid(self):
        return bool(self.upload_finished)

    @property
    def url(self):
        return self.file.url
