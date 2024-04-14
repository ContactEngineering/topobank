from django.db import transaction
from django.utils import timezone

from topobank.manager.models import FileManifest, FileParent
from topobank.manager.utils import generate_file_name, generate_upload_path, get_upload_instructions
from topobank.users.models import User


class FileUploadService:

    def __init__(self, user: User, expire=100):
        self.user = user
        self.expire = expire

    @transaction.atomic
    def start(self, *, file_name: str, file_type: str, parent: FileParent, kind: str):
        file_manifest = FileManifest(
                original_file_name=file_name,
                file_name=generate_file_name(file_name),
                file_type=file_type,
                kind=kind,
                uploaded_by=self.user,
                parent=parent,
                file=None
        )
        file_manifest.full_clean()
        file_manifest.save()

        upload_path = generate_upload_path(file_manifest, file_manifest.original_file_name)
        file_manifest.file = file_manifest.file.field.attr_class(file_manifest, file_manifest.file.field, upload_path)
        file_manifest.save()

        upload_instructions = get_upload_instructions(None, upload_path, self.expire)

        return {'id': file_manifest.id, **upload_instructions}

    @transaction.atomic
    def finish(self, *, file_manifest: FileManifest) -> FileManifest:
        file_manifest.upload_finished = timezone.now()
        file_manifest.full_clean()
        file_manifest.save()

        return file_manifest
