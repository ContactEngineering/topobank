"""
Repair attachment folders whose permissions do not match their dataset.

Attachments are visible to exactly the users who may see the surface or
topography they belong to, because folder and files share its permission set.
Copies made before the fixes in 0fbd9a21 (2024-12-11) and 9b7acdd9 (2025-01-23)
broke that (topobank#1414), and copies are how datasets are published:

- Surface.deepcopy copied the attachment folder but kept the permission set of
  the original, private surface;
- Topography.deepcopy did not copy the attachment folder at all, so the copy
  and the original refer to the same folder.

Listing the attachments of such a published dataset is a 404 for everyone who
could not see the original.

A folder used only by the object whose permissions it lacks is switched to the
object's permission set. A folder shared between objects with different
permission sets cannot be: whatever it is switched to, one of them loses
access or the other one's attachments become visible to too many users. Every
object whose permissions differ from the shared folder's gets a copy of the
folder with its own permission set instead.
"""

import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from topobank.manager.models import Surface, Topography

_log = logging.getLogger(__name__)

MODELS = (Surface, Topography)


def _referrers(folder_id):
    """All surfaces and topographies (including deleted ones) using a folder."""
    return [
        obj
        for model in MODELS
        for obj in model.all_objects.filter(attachments_id=folder_id)
    ]


def _mismatched(model):
    """Objects whose attachment folder or files lack the object's permissions."""
    for obj in model.all_objects.filter(attachments__isnull=False).select_related(
        "attachments"
    ):
        folder = obj.attachments
        if (
            folder.permissions_id != obj.permissions_id
            or folder.files.exclude(permissions_id=obj.permissions_id).exists()
        ):
            yield obj


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Only report what would be changed.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        nb_switched = 0
        nb_copied = 0

        for model in MODELS:
            for obj in list(_mismatched(model)):
                folder = obj.attachments
                referrers = _referrers(folder.id)
                label = f"{model.__name__} {obj.id} (attachments folder {folder.id})"

                if len(referrers) == 1:
                    self.stdout.write(f"{label}: switching folder to its permissions")
                    nb_switched += 1
                    if not dry_run:
                        with transaction.atomic():
                            folder.permissions_id = obj.permissions_id
                            folder.save(update_fields=["permissions"])
                            folder.files.update(permissions_id=obj.permissions_id)
                else:
                    self.stdout.write(
                        f"{label}: folder is shared with "
                        f"{len(referrers) - 1} other object(s), copying it"
                    )
                    nb_copied += 1
                    if not dry_run:
                        with transaction.atomic():
                            copy = folder.deepcopy(permissions=obj.permissions)
                            # Bypass save() and its signals, only the folder changes
                            model.all_objects.filter(pk=obj.pk).update(attachments=copy)

        self.stdout.write(
            self.style.SUCCESS(
                f"Folders switched to their object's permissions: {nb_switched}"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(f"Shared folders copied for an object: {nb_copied}")
        )
        if dry_run:
            self.stdout.write(
                self.style.WARNING("This was a dry run, nothing has been changed.")
            )
        else:
            self.stdout.write(self.style.SUCCESS("Done."))
