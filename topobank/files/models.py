"""
Basic models for the web app for handling topography data.
"""

import logging

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import models
from rest_framework.reverse import reverse
from storages.utils import clean_name

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

    FILE_KIND_CHOICES = [
        ("N/A", "Kind is unknown"),
        ("att", "Attachment"),  # Attachments are not processed by the system
        ("der", "Data derived from a raw data file"),
        ("raw", "Raw data file as uploaded by a user"),
    ]

    file = models.FileField(upload_to=generate_storage_path, blank=True, null=True)
    filename = models.CharField(max_length=255)

    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    # Folder can be null, in which case this is a single file that belongs to some
    # model (e.g. a raw data file or a thumbnail of a measurement)
    folder = models.ForeignKey(
        Folder, related_name="files", on_delete=models.CASCADE, null=True
    )
    kind = models.CharField(max_length=3, choices=FILE_KIND_CHOICES, default="N/A")

    upload_finished = models.DateTimeField(blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"File {self.filename}"

    @property
    def is_valid(self):
        return bool(self.upload_finished)

    @property
    def url(self):
        return self.file.url

    def get_upload_instructions(self, expire=10, method=None):
        """Generate a presigned URL for an upload directly to S3"""
        # Preserve the trailing slash after normalizing the path.
        if method is None:
            method = settings.UPLOAD_METHOD

        if settings.USE_S3_STORAGE:
            name = default_storage._normalize_name(clean_name(self.file_name))
            if method == "POST":
                upload_instructions = (
                    default_storage.bucket.meta.client.generate_presigned_post(
                        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                        Key=name,
                        ExpiresIn=expire,
                    )
                )
                upload_instructions["method"] = "POST"
            elif method == "PUT":
                upload_instructions = {
                    "method": "PUT",
                    "url": default_storage.bucket.meta.client.generate_presigned_url(
                        ClientMethod="put_object",
                        Params={
                            "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                            "Key": name,
                            # ContentType must match content type of put request
                            "ContentType": "binary/octet-stream",
                        },
                        ExpiresIn=expire,
                    ),
                }
            else:
                raise RuntimeError(f"Unknown upload method: {method}")
        else:
            if method != "POST":
                raise RuntimeError("Only POST uploads are supported without S3")
            upload_instructions = {
                "method": "POST",
                "url": reverse(
                    "files:upload-direct-local", kwargs=dict(manifest_id=self.id)
                ),
                "fields": {},
            }
        return upload_instructions
