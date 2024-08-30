"""
Basic models for the web app for handling topography data.
"""

import logging

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import models
from django.utils import timezone

from ..authorization.mixins import PermissionMixin
from ..authorization.models import AuthorizedManager, PermissionSet
from .utils import generate_storage_path

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

    def save_file(self, filename, kind, fobj):
        Manifest.objects.create(
            permissions=self.permissions, filename=filename, kind=kind, file=fobj
        )

    def get_files(self) -> models.QuerySet["Manifest"]:
        return self.files.all()

    def get_valid_files(self) -> models.QuerySet["Manifest"]:
        # NOTE: "files" is the reverse `related_name` for the relation to `FileManifest`
        return self.get_files().filter(upload_confirmed__isnull=False)

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

    #
    # Model data
    #

    FILE_KIND_CHOICES = [
        ("N/A", "Kind is unknown"),
        ("att", "Attachment"),  # Attachments are not processed by the system
        ("der", "Data derived from a raw data file"),
        ("raw", "Raw data file as uploaded by a user"),
    ]

    # The actual file
    file = models.FileField(upload_to=generate_storage_path, blank=True, null=True)
    # The name of the file without any storage location
    filename = models.CharField(max_length=255)  # The filename

    # User that uploaded this file (if the file is not automatically generated as
    # indicated by file kind "der")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )

    # Folder can be null, in which case this is a single file that belongs to some
    # model (e.g. a raw data file or a thumbnail of a measurement)
    folder = models.ForeignKey(
        Folder, related_name="files", on_delete=models.CASCADE, null=True
    )

    # File kind, indicating where the file came from
    kind = models.CharField(max_length=3, choices=FILE_KIND_CHOICES, default="N/A")

    #
    # Dates - all three dates are typically similar
    #

    # The date the upload was confirmed by the `finish_upload` method. This is typically
    # the date the file was uploaded.
    upload_confirmed = models.DateTimeField(blank=True, null=True)
    # The date the manifest was created
    created = models.DateTimeField(auto_now_add=True)
    # The date the manifest was last updated
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Manifest for file {self.filename}"

    @property
    def url(self):
        return self.file.url

    def finish_upload(self, file=None):
        if file is None:
            if not settings.USE_S3_STORAGE:
                # Do nothing; without S3 uploads are finished through a special route
                # that provides the file here
                return
            storage_path = generate_storage_path(self, self.filename)
            if default_storage.exists(storage_path):
                # Set storage location to file that was just uploaded
                self.file = self.file.field.attr_class(
                    self, self.file.field, storage_path
                )
        else:
            self.file.save(self.filename, file, save=False)

        self.upload_confirmed = timezone.now()
        self.save()

    def exists(self):
        """Check if a file exists"""
        if not bool(self.file):
            self.finish_upload()
        return bool(self.file)

    def assert_exists(self):
        if not self.exists():
            raise OSError(
                f"Manifest {self.id} does not have a file associated with it."
            )

    def open(self, *args, **kwargs):
        self.assert_exists()
        return self.file.open(*args, **kwargs)

    def read(self, *args, **kwargs):
        self.assert_exists()
        return self.file.read(*args, **kwargs)

    def save_file(self, fobj):
        if self.exists():
            self.file.delete()
        self.file.save(self.filename, fobj)

    def deepcopy(self, permissions=None):
        copy = Manifest.objects.get(pk=self.pk)
        copy.pk = None  # This will lead to the creation of a new instance on save
        copy.file = None
        copy.folder = None

        # Set permissions
        if permissions is not None:
            copy.permissions = permissions

        # Save to get a pk
        copy.save()

        # Copy the actual data file
        with self.file.open(mode="rb") as file:
            copy.save_file(file)

        # Save again
        copy.save()

        return copy
