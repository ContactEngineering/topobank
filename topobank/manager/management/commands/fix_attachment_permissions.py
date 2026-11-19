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

Only files that existed when the dataset was published are made visible. The
private original stays editable, so its owner may have added or replaced
attachments in a shared folder after publication; those were never part of the
publication and must not become public. A file created, changed or confirmed
after publication is therefore left out of a copy, and a folder of a single
object that contains such a file is not switched at all. Both are reported, for
an admin to review.
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from topobank.files.models import Manifest, ManifestSet
from topobank.manager.models import Surface, Topography

_log = logging.getLogger(__name__)

MODELS = (Surface, Topography)

#: Without a publication, a copy counts as made this long after its row was
#: created: copying the files of a dataset happens after the row is saved.
COPY_TOLERANCE = timedelta(hours=1)


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


def _published_at(obj):
    """
    When the dataset of `obj` was published, i.e. when its copy was complete;
    `None` if unknown.

    The publication is created only after the copy has finished, so it is later
    than every file the copy made. Without a publication (e.g. the publication
    plugin is not installed), fall back to the copied surface's creation time,
    also for a topography: a topography's `created_at` was added by migration
    0072 and holds the migration's time for every older topography, while the
    surface's was only renamed and is the copy's.
    """
    surface = obj if isinstance(obj, Surface) else obj.surface
    try:
        published_at = surface.publication.datetime
    except Exception:  # no publication, or no publication plugin
        published_at = None
    if published_at is not None:
        return published_at
    if surface.created_at is not None:
        return surface.created_at + COPY_TOLERANCE
    return None


def _last_change(manifest):
    times = [manifest.created_at, manifest.updated_at, manifest.confirmed_at]
    return max(t for t in times if t is not None)


def _split_by_publication(folder, published_at):
    """Files of `folder` from before and after publication (or of unknown age)."""
    before, after = [], []
    for manifest in folder.files.all():
        if published_at is not None and _last_change(manifest) <= published_at:
            before.append(manifest)
        else:
            after.append(manifest)
    return before, after


class ChangedDuringCopy(Exception):
    """A source file was replaced while it was being copied."""

    def __init__(self, manifest):
        super().__init__(manifest)
        self.manifest = manifest


def _stored_state(manifest):
    """What identifies the bytes of `manifest` in storage: their name and when
    they were written. A replacement changes one of the two, also one that
    writes storage before its manifest row (a direct upload)."""
    name = manifest.file.name
    return name, manifest.file.storage.get_modified_time(name)


def _copy_folder(folder, manifests, permissions):
    """A copy of `folder` with only the given (valid) files and `permissions`.

    The age of each file was checked before, but its owner may replace it
    while it is copied, and storage is outside any transaction. So each file's
    stored bytes and manifest row are compared before and after it is copied;
    if either changed, the copied files are deleted and `ChangedDuringCopy` is
    raised, for the caller's transaction to roll back. The manifest rows are
    locked meanwhile, so a replacement cannot record itself before the
    comparison has seen its bytes.
    """
    copy = ManifestSet.objects.get(pk=folder.pk)
    copy.pk = None
    copy.permissions = permissions
    copy.save()
    copies = []
    try:
        locked = Manifest.objects.select_for_update().in_bulk(
            [m.pk for m in manifests]
        )
        for manifest in manifests:
            manifest = locked.get(manifest.pk)
            if manifest is None or manifest.confirmed_at is None:
                continue  # gone, or unfinished upload, as in ManifestSet.deepcopy
            before = (_stored_state(manifest), _last_change(manifest))
            manifest_copy = manifest.deepcopy(permissions=permissions)
            copies.append(manifest_copy)
            manifest_copy.folder = copy
            manifest_copy.save()
            manifest.refresh_from_db()
            if (_stored_state(manifest), _last_change(manifest)) != before:
                raise ChangedDuringCopy(manifest)
    except Exception:
        for manifest_copy in copies:
            manifest_copy.file.delete(save=False)
        raise
    return copy


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Only report what would be changed.",
        )

    def _review(
        self,
        label,
        manifests,
        reason="added or changed after publication or of unknown age",
    ):
        names = ", ".join(f"'{m.filename}' (manifest {m.pk})" for m in manifests)
        self.stdout.write(
            self.style.WARNING(
                f"{label}: NEEDS REVIEW, {len(manifests)} file(s) {reason} "
                f"were not made visible: {names}"
            )
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        nb_switched = 0
        nb_copied = 0
        nb_review = 0

        for model in MODELS:
            for obj in list(_mismatched(model)):
                folder = obj.attachments
                referrers = _referrers(folder.id)
                label = f"{model.__name__} {obj.id} (attachments folder {folder.id})"
                before, after = _split_by_publication(folder, _published_at(obj))

                if len(referrers) == 1:
                    if after:
                        # Switching the folder would publish these files too
                        self._review(f"{label}: not switched", after)
                        nb_review += 1
                        continue
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
                        f"{len(referrers) - 1} other object(s), copying the "
                        f"{len(before)} file(s) from before publication"
                    )
                    nb_copied += 1
                    if after:
                        self._review(f"{label}: left out of the copy", after)
                        nb_review += 1
                    if not dry_run:
                        try:
                            with transaction.atomic():
                                copy = _copy_folder(folder, before, obj.permissions)
                                # Bypass save() and its signals, only the folder
                                # changes
                                model.all_objects.filter(pk=obj.pk).update(
                                    attachments=copy
                                )
                        except ChangedDuringCopy as exc:
                            nb_copied -= 1
                            nb_review += 1
                            self._review(
                                f"{label}: not copied, run the command again",
                                [exc.manifest],
                                reason="changed while being copied",
                            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Folders switched to their object's permissions: {nb_switched}"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(f"Shared folders copied for an object: {nb_copied}")
        )
        self.stdout.write(
            self.style.SUCCESS(f"Folders with files that need review: {nb_review}")
        )
        if dry_run:
            self.stdout.write(
                self.style.WARNING("This was a dry run, nothing has been changed.")
            )
        else:
            self.stdout.write(self.style.SUCCESS("Done."))
