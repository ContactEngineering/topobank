import logging
from typing import Union

from django.db import transaction
from django.utils import timezone

from topobank.files.models import Folder, Manifest
from topobank.users.models import User

_log = logging.getLogger(__name__)


class FileUploadService:

    def __init__(self, user: User, expire: int = 10):
        self.user = user
        self.expire = expire

    @transaction.atomic
    def start(
        self,
        *,
        filename: str,
        folder: Union[Folder, None] = None,
        kind: str = "raw"
    ):
        manifest = Manifest(
            filename=filename,
            kind=kind,
            uploaded_by=self.user,
            folder=folder,
            file=None,
        )
        manifest.full_clean()
        # Need to save so we have an id for the upload path generation
        manifest.save()

        # Return upload instructions
        _log.debug(
            f"Prepared to receive file for manifest {manifest} at storage location "
            f"{manifest.file.path}."
        )
        return manifest.get_upload_instructions(self.expire)

    @transaction.atomic
    def finish(self, *, manifest: Manifest) -> Manifest:
        manifest.upload_finished = timezone.now()
        manifest.full_clean()
        manifest.save()

        return manifest

    @transaction.atomic
    def upload_local(self, *, manifest: Manifest, file) -> Manifest:
        manifest.file = file
        manifest.full_clean()
        manifest.save()

        return file
