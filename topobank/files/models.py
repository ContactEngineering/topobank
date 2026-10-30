"""
Basic models for handling files and folders, including upload/download logic.
"""

import io
import json
import logging
import os
from tempfile import NamedTemporaryFile

import xarray
from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import models
from django.db.models import Q, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from storages.utils import clean_name

from ..authorization.mixins import PermissionMixin
from ..authorization.models import AuthorizedManager
from ..supplib.json import ExtendedJSONEncoder
from .utils import file_storage_path

_log = logging.getLogger(__name__)


class ManifestSet(PermissionMixin, models.Model):
    #
    # Manager
    #
    objects = AuthorizedManager()

    #
    # Permissions
    #
    permissions = models.ForeignKey(
        getattr(settings, 'TOPOBANK_PERMISSION_MODEL', 'authorization.PermissionSet'),
        on_delete=models.CASCADE, null=True
    )

    #
    # ManifestSet parameters
    #
    read_only = models.BooleanField("read_only", default=True)

    def __str__(self) -> str:
        return "ManifestSet"

    def __len__(self) -> int:
        return self.files.count()

    def __getitem__(self, item):
        return self.files.all()[item]

    def open_file(self, filename: str, mode: str = "r"):
        try:
            manifest = self.files.get(filename=filename)
        except Manifest.DoesNotExist:
            raise FileNotFoundError(
                f"Manifest for file '{filename}' not found in folder"
            )
        return manifest.open(mode)

    def read_json(self, filename: str) -> dict:
        with self.open_file(filename) as f:
            return json.load(f)

    def read_xarray(self, filename: str) -> xarray.Dataset:
        with self.open_file(filename, mode="rb") as f:
            # We need to wrap this in a BytesIO object because xarray query the `path`
            # property of the stream, which is not supported by the S3 storage backend.
            return xarray.load_dataset(io.BytesIO(f.read()), engine="scipy")

    def save_file(self, filename: str, kind: str, fobj):
        # Check whether file exists in this folder, and delete if it does
        fobj.name = filename  # Make sure the filenames are the same
        try:
            manifest = self.files.get(filename=filename)
            created = False
        except Manifest.DoesNotExist:
            manifest = Manifest.objects.create(filename=filename)
            created = True
        manifest.permissions = self.permissions
        manifest.folder = self
        manifest.kind = kind
        if not created:
            manifest.file.delete()
        manifest.file = fobj
        manifest.confirmed_at = timezone.now()
        manifest.save()

    def save_json(self, filename: str, data):
        self.save_file(filename, "der", ContentFile(json.dumps(data, cls=ExtendedJSONEncoder)))

    def save_xarray(self, filename: str, data: xarray.Dataset):
        with NamedTemporaryFile(delete=False) as f:
            # NetCDF mess: NetCDF closes the file after write, so we need to make sure
            # we can reopen it to store it in the backend.
            # FIXME(pastewka): Think about monkey-patching xarray. Look at NC.py of
            # SurfaceTopography to see how to avoid closing of the stream with the
            # scipy reader.
            data.to_netcdf(f, format="NETCDF3_CLASSIC")
            with open(f.name, "rb") as f2:
                self.save_file(filename, "der", ContentFile(f2.read()))
            # FIXME(pastewka): Starting with Python 3.12, we can simply use
            # delete_on_close=False in NamedTemporaryFile and get rid of explicitly
            # deleting the file.
            os.remove(f.name)

    def exists(self, filename: str) -> bool:
        return self.files.filter(filename=filename).count() > 0

    def get_files(self) -> models.QuerySet["Manifest"]:
        return self.files.all()

    def get_valid_files(self) -> models.QuerySet["Manifest"]:
        # NOTE: "files" is the reverse `related_name` for the relation to `FileManifest`
        return self.get_files().filter(confirmed_at__isnull=False)

    def find_file(self, filename: str) -> "Manifest":
        return self.files.get(filename=filename)

    def remove_files(self):
        """Clear this folder by removing all files."""
        self.files.all().delete()

    def deepcopy(self, permissions=None):
        copy = ManifestSet.objects.get(pk=self.pk)
        copy.pk = None
        if permissions is not None:
            copy.permissions = permissions
        copy.save()

        for filemanifest in self.get_valid_files():
            filemanifest_copy = filemanifest.deepcopy(permissions=permissions)
            filemanifest_copy.folder = copy
            filemanifest_copy.save()

        return copy


# The Flow for "direct file upload" is heavily inspired from here:
# https://www.hacksoft.io/blog/direct-to-s3-file-upload-with-django
class Manifest(PermissionMixin, models.Model):
    class Meta:
        unique_together = (("folder", "filename"),)
        indexes = [
            # Partial index for the custodian sweep over unconfirmed attachments
            # (kind="att" AND confirmed_at IS NULL), ordered by age. Only reserved
            # uploads that never completed are indexed, so it stays small.
            models.Index(
                fields=["created_at"],
                name="manifest_unconfirmed_att_idx",
                condition=Q(kind="att", confirmed_at__isnull=True),
            ),
        ]

    #
    # Manager
    #
    objects = AuthorizedManager()

    #
    # Permissions
    #
    permissions = models.ForeignKey(
        getattr(settings, 'TOPOBANK_PERMISSION_MODEL', 'authorization.PermissionSet'),
        on_delete=models.CASCADE, null=True
    )

    #
    # Model data
    #

    # Where a file came from. The distinction that matters is *who* produced it:
    # "raw" and "att" are both uploaded by a person, "der" is produced by the
    # system. So "did a user put this here?" is answerable from `kind` alone, and
    # nothing else needs to carry that fact.
    #
    # Do not stamp "att" on generated output. An attachment is a file a user
    # attached to a dataset or measurement - a spec sheet, a photo of a defect, a
    # supplier certificate - and the system does not process it. Anything the
    # system writes is "der", including reports and rendered images, even when it
    # writes them into a `ManifestSet` that also holds user attachments.
    FILE_KIND_CHOICES = [
        ("N/A", "Kind is unknown"),
        ("att", "File attachment uploaded by a user"),
        ("der", "Data derived from a raw data file"),
        ("raw", "Raw data file as uploaded by a user"),
    ]

    # The actual file
    file = models.FileField(
        upload_to=file_storage_path, max_length=512, blank=True, null=True
    )
    # The name of the file without any storage location
    filename = models.CharField(max_length=255)  # The filename

    # User that uploaded this file (if the file is not automatically generated as
    # indicated by file kind "der")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    folder = models.ForeignKey(
        ManifestSet, on_delete=models.CASCADE, related_name="files", null=True
    )

    # File kind, indicating where the file came from
    kind = models.CharField(max_length=3, choices=FILE_KIND_CHOICES, default="N/A")

    #
    # Descriptive metadata
    #

    # Free-text annotation supplied by whoever uploaded the file: what it is, why
    # it is attached. Purely informational - nothing reads it to make a decision.
    note = models.TextField(blank=True, default="")

    # Size of the file in bytes, as reported by the client before the upload.
    #
    # Storage remains the source of truth: this is a convenience for listings that
    # would otherwise have to stat every object, and callers that presign an upload
    # can only know the size the client claimed. Overwrite it with `file.size` once
    # the upload is confirmed. None means "not reported" - typically an upload that
    # has been reserved but not yet confirmed.
    size_bytes = models.PositiveBigIntegerField(blank=True, null=True)

    # MIME type the object is stored with.
    #
    # Whoever creates the manifest decides this, and for a presigned upload it is
    # baked into the policy - so it governs what a bare presigned GET serves, and
    # therefore whether a browser will render the file inline. Derive it rather
    # than trusting a client-declared value.
    content_type = models.CharField(max_length=127, blank=True, default="")

    #
    # Dates - all three dates are typically similar
    #

    # The date the upload was confirmed (see `confirm_upload`). This is typically
    # the date the file was uploaded.
    confirmed_at = models.DateTimeField(blank=True, null=True)
    # The date the manifest was created
    created_at = models.DateTimeField(auto_now_add=True)
    # The date the manifest was last updated
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Manifest <{self.filename}>"

    @property
    def url(self):
        return self.file.url

    def confirm_upload(self, *, raise_storage_errors=False) -> bool:
        """Record the uploaded file on this manifest, once it has arrived.

        A manifest created ahead of a direct-to-storage upload has no file until
        the object turns up at its storage path. This looks for it and, if it is
        there, sets `file`, `confirmed_at` and `size_bytes`. Confirming is done
        once: of concurrent callers one writes the confirmation and the others
        read it back, so `confirmed_at` is never overwritten.

        Returns whether the manifest has a file. Unlike `exists`, which only
        checks the manifest, this looks in storage. Storage that cannot be asked
        (unreachable, or refusing) leaves the upload unconfirmed, as a missing
        file does, unless `raise_storage_errors` is set: then the storage's
        error is raised, for a caller that must tell the two apart.
        """
        if self.file:
            return True
        if self.pk is None:
            return False
        try:
            storage_path = self.generate_storage_path()
        except SuspiciousFileOperation:
            # Could not create a storage path! This is likely because the file
            # name is invalid
            _log.info(
                f"Manifest {self.id} has no file associated with it, and the "
                f"filename '{self.filename}' appears invalid. Cannot confirm the "
                "upload."
            )
            return False
        _log.debug(
            f"Manifest {self.id} has no file associated with it. Checking if one "
            f"exists at the likely storage location '{storage_path}'..."
        )
        # One round trip to storage: the size tells whether the file is there
        try:
            size_bytes = default_storage.size(storage_path)
        except FileNotFoundError:
            _log.debug("...no file found. Cannot confirm the upload.")
            return False
        except Exception as exc:
            # Storage is unreachable or refuses: not confirmed for now, rather
            # than confirmed on a guess. The next read tries again.
            if raise_storage_errors:
                raise
            _log.warning(
                "Could not check for the file of manifest %s at '%s': %s",
                self.id,
                storage_path,
                exc,
            )
            return False
        _log.debug("...found file, updating manifest.")
        now = timezone.now()
        # Only a manifest without a file is confirmed, and `confirmed_at` is kept
        # where it was already set (a copy whose file never arrived, say)
        confirmed = (
            Manifest.objects.filter(pk=self.pk)
            .filter(Q(file__isnull=True) | Q(file=""))
            .update(
                file=storage_path,
                size_bytes=size_bytes,
                confirmed_at=Coalesce("confirmed_at", Value(now)),
            )
        )
        if confirmed:
            self.file = self.file.field.attr_class(self, self.file.field, storage_path)
            self.size_bytes = size_bytes
            if self.confirmed_at is None:
                self.confirmed_at = now
        else:
            # Someone else confirmed it first
            self.refresh_from_db(fields=["file", "confirmed_at", "size_bytes"])
        return bool(self.file)

    def finish_upload(self, file=None):
        """Confirm the upload (see `confirm_upload`), or store `file` as it."""
        if file is None:
            self.confirm_upload()
        else:
            self.save_file(file)

    def exists(self):
        """Whether the manifest has a file.

        Only checks the manifest. An upload that has arrived but is not confirmed
        yet has none; `confirm_upload` looks for it in storage.
        """
        return bool(self.file)

    is_valid = exists

    def _file_or_raise(self):
        """The file, confirming an upload that has arrived (see `confirm_upload`)."""
        if not self.confirm_upload():
            raise OSError(
                f"Manifest {self.id} does not have a file associated with it."
            )
        return self.file

    def open(self, *args, **kwargs):
        return self._file_or_raise().open(*args, **kwargs)

    def read(self, *args, **kwargs):
        return self._file_or_raise().read(*args, **kwargs)

    def save(self, *args, **kwargs):
        created = self.pk is not None  # True on creation of the manifest
        file = None
        if not created and self.file:
            # We have a file but no id yet hence cannot create a storage path
            file = self.file
            self.file = None
        super().save(*args, **kwargs)
        if file:
            # Now set the file name; we have an id and can create a storage path and
            # upload the file
            self.file = file
            super().save(update_fields=["file"])
        # We have no file but a file name; make sure no file with the same name already
        # exists at the targeted storage location
        if not created and not self.file and self.filename:
            # We just created this manifest and no file was passed on creation
            try:
                storage_path = self.generate_storage_path()
            except SuspiciousFileOperation:
                # We ignore this
                _log.info(
                    f"Manifest {self.id} has no file associated with it, and the "
                    f"filename '{self.filename}' appears invalid."
                )
                return
            if default_storage.exists(storage_path):
                if settings.DELETE_EXISTING_FILES:
                    default_storage.delete(storage_path)
                else:
                    raise RuntimeError(
                        "A new manifest was generated, but an existing file was found "
                        f"at the storage path {storage_path}. Set "
                        f"DELETE_EXISTING_FILES to True to ignore this error."
                    )

    def save_file(self, fobj, size_bytes=None):
        """Store `fobj` as this manifest's file, replacing the file it has.

        The manifest is confirmed with it: a file stored by the application
        itself is as confirmed as an upload that was found in storage. Pass
        `size_bytes` where the caller knows it, so that storage need not be asked.
        """
        if self.file:
            # The reference goes with the file: should storing the new file
            # fail, the manifest must not keep pointing at a deleted one
            self.file.delete(save=False)
            self.save(update_fields=["file"])
        self.file.save(self.filename, fobj, save=False)
        self.confirmed_at = timezone.now()
        # The size of an in-memory or local file comes from the content; only
        # for a file that lives in storage would `fobj.size` ask storage
        if size_bytes is None:
            size_bytes = getattr(fobj, "size", None)
        self.size_bytes = size_bytes if size_bytes is not None else self.file.size
        self.save(update_fields=["file", "confirmed_at", "size_bytes"])

    def deepcopy(self, permissions=None):
        copy = Manifest.objects.get(pk=self.pk)
        copy.pk = None  # This will lead to the creation of a new instance on save
        copy.file = None
        # Confirmed once its own file is in place (see `save_file`), not before
        copy.confirmed_at = None
        copy.size_bytes = None
        copy.folder = None  # Caller is responsible for assigning to a folder

        # Set permissions
        if permissions is not None:
            copy.permissions = permissions

        # Save to get a pk
        copy.save()

        # Copy the actual data file; its size is known, storage need not be asked
        with self.file.open(mode="rb") as file:
            copy.save_file(file, size_bytes=self.size_bytes)

        # Save again
        copy.save()

        return copy

    def generate_storage_path(self):
        """Full path of the file on the storage backend"""
        return self.file.field.generate_filename(self, clean_name(self.filename))
