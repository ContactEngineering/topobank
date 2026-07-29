import logging
import tempfile
import zipfile

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils.text import slugify

from ..authorization.mixins import PermissionMixin
from ..authorization.models import AuthorizedManager
from ..files.models import Manifest
from ..taskapp.models import TaskStateModel
from .export_zip import export_container_zip
from .import_zip import import_container_zip
from .models import Surface, Tag

_log = logging.getLogger(__name__)



class ZipContainer(PermissionMixin, TaskStateModel):
    #
    # Celery task queue
    #
    celery_queue = settings.TOPOBANK_MANAGER_QUEUE

    #
    # Manager
    #
    objects = AuthorizedManager()

    #
    # Model hierarchy and permissions
    #
    permissions = models.ForeignKey(
        getattr(settings, 'TOPOBANK_PERMISSION_MODEL', 'authorization.PermissionSet'),
        on_delete=models.CASCADE, null=True
    )

    # The file itself
    manifest = models.ForeignKey(
        Manifest,
        null=True,
        on_delete=models.SET_NULL,
        related_name="zip_containers",
    )

    # Timestamp of creation of this ZIP container
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def create_empty_manifest(self):
        if self.manifest is not None:
            raise RuntimeError(
                "This ZIP container already has a manifest. Cannot create a new one."
            )
        self.manifest = Manifest.objects.create(
            permissions=self.permissions, filename="container.zip", kind="raw"
        )
        self.save(update_fields=["manifest"])

    def export_zip(
        self,
        tag_name=None,
        surface_ids=None,
        archive_name=None,
        extra_metadata=None,
        progress_recorder=None,
    ):
        """
        Bundle datasets into a ZIP archive and store it on this container's
        manifest.

        Parameters
        ----------
        tag_name : str, optional
            Bundle every dataset below this tag. Mutually exclusive with
            `surface_ids`. (Default: None)
        surface_ids : list of int, optional
            Bundle these datasets. Mutually exclusive with `tag_name`.
            (Default: None)
        archive_name : str, optional
            Human-readable name for the archive; it is slugified into the file
            name. Deployments that group datasets by something other than tags
            (e.g. folders) use this to name the download after that grouping.
            Falls back to a name derived from the datasets themselves.
            (Default: None)
        extra_metadata : dict, optional
            Opaque payload written to the container metadata, see
            `export_container_zip`. Surface references therein should use
            indices into the container's dataset order, which is the order of
            `surface_ids`. (Default: None)
        progress_recorder : topobank.taskapp.tasks.ProgressRecorder, optional
            Reports how many measurements have been bundled so far.
            (Default: None)

        Returns
        -------
        None
        """
        #
        # Fetch user
        #
        user = self.permissions.user_permissions.first().user

        #
        # Fetch tag (if present)
        #
        if tag_name is not None:
            tag = Tag.objects.get(name=tag_name)
            tag.authorize_user(user, "view")
            surfaces = list(tag.get_descendant_surfaces())
        elif surface_ids is not None:
            surfaces = [Surface.objects.get(id=id) for id in surface_ids]
            for surface in surfaces:
                if not surface.has_permission(user, "view"):
                    raise PermissionDenied()
        else:
            raise RuntimeError("Please specify either a tag id or dataset ids.")

        #
        # Idiot check
        #
        if not len(surfaces) > 0:
            raise RuntimeError("Please specify at least one dataset.")

        #
        # Guess a filename
        #
        archive_slug = slugify(archive_name) if archive_name else ""
        if archive_slug:
            container_filename = f"{archive_slug}.zip"
        elif len(surfaces) == 1:
            container_filename = f"{slugify(surfaces[0].name)}.zip"
        else:
            container_filename = "digital-surface-twins.zip"

        _log.info(
            f"Preparing container of surface with ids {' '.join([str(s.id) for s in surfaces])} for download..."
        )
        max_size = getattr(settings, "TOPOBANK_SPOOL_MAX_SIZE", 64 * 1024 * 1024)
        with tempfile.SpooledTemporaryFile(max_size=max_size) as container_data:
            try:
                export_container_zip(
                    container_data,
                    surfaces,
                    extra_metadata=extra_metadata,
                    progress_recorder=progress_recorder,
                )
            except FileNotFoundError:
                # Raise, don't return: returning the exception left the task in
                # SUCCESS with no manifest, so a client would be told its
                # download was ready and then find nothing to fetch.
                raise RuntimeError(
                    "Cannot create ZIP container for download because some data file "
                    "could not be accessed. (The file may be missing.)"
                )
            container_data.seek(0)

            #
            # Create and write the file to storage
            #
            self.manifest = Manifest.objects.create(
                permissions=self.permissions,
                filename=container_filename,
                kind="der",
            )
            self.manifest.save_file(container_data)

    def import_zip(self):
        _log.info(f"Importing ZIP container '{self.manifest.file.name}'...")
        permission = self.permissions.user_permissions.first()
        if permission.allow != "full":
            raise PermissionDenied(
                "Internal error: The single user for ZIP uploads should have full permission."
            )
        with zipfile.ZipFile(self.manifest.file, mode='r') as z:
            import_container_zip(z, permission.user, ignore_missing=True)

    def task_worker(
        self,
        tag_name=None,
        surface_ids=None,
        archive_name=None,
        extra_metadata=None,
        progress_recorder=None,
    ):
        if self.permissions.user_permissions.count() != 1:
            raise PermissionDenied(
                "Internal error: There should only be a single user for ZIP downloads and uploads."
            )

        if self.manifest is None and (tag_name is not None or surface_ids is not None):
            # There is no file, but we have a tag or a list of datasets
            self.export_zip(
                tag_name=tag_name,
                surface_ids=surface_ids,
                archive_name=archive_name,
                extra_metadata=extra_metadata,
                progress_recorder=progress_recorder,
            )
        elif self.manifest is not None and self.manifest.exists():
            # There is a file, which means we should try to import
            self.import_zip()
        else:
            # Nothing to do? Maybe we are still waiting for a file upload?
            _log.info("Nothing to do.")
