"""
Move each measurement's derived files into its `derived` folder, and record its
kind.

The deep zoom folder of a map becomes its derived folder; a line scan (or a map
without deep zoom images) gets a new, empty one. The thumbnail and the squeezed
datafile are moved into it under the names the processing steps give them
(`thumbnail.<format>`, `squeezed.nc`). Nothing is copied in storage: a manifest's
storage key does not depend on its folder or its name. The deprecated fields
`thumbnail`, `squeezed_datafile` and `deepzoom` keep pointing at the same rows.

Each derived file found is recorded as written by version 1 of its built-in step
(`ProcessingStepRecord`), so that the files of a deployment that runs just the
built-in steps count as up to date.

The kind follows from the columns for an inspected measurement: a map has a
`resolution_y`; a line scan is nonuniform if the inspection made its periodicity
uneditable, which it does for exactly the nonuniform ones. Measurements that were
never inspected stay without a kind until they are.
"""

import os

from django.db import migrations
from django.db.models import Q

BATCH_SIZE = 1000

SQUEEZED_FILENAME = "squeezed.nc"
THUMBNAIL_STEM = "thumbnail"


def backfill_kind(apps, schema_editor):
    Topography = apps.get_model("manager", "Topography")
    rows = Topography._base_manager.filter(kind__isnull=True, resolution_x__isnull=False)
    rows.filter(resolution_y__isnull=False).update(kind="topography-map")
    rows = rows.filter(resolution_y__isnull=True)
    rows.filter(is_periodic_editable=False).update(kind="nonuniform-line-scan")
    rows.filter(is_periodic_editable=True).update(kind="uniform-line-scan")


def _thumbnail_filename(manifest):
    _, ext = os.path.splitext(manifest.filename)
    return f"{THUMBNAIL_STEM}{ext or '.jpeg'}"


def move_into_derived_folder(apps, schema_editor):
    Topography = apps.get_model("manager", "Topography")
    ProcessingStepRecord = apps.get_model("manager", "ProcessingStepRecord")
    Manifest = apps.get_model("files", "Manifest")
    ManifestSet = apps.get_model("files", "ManifestSet")

    rows = (
        Topography._base_manager.filter(derived__isnull=True)
        .filter(
            Q(thumbnail__isnull=False)
            | Q(squeezed_datafile__isnull=False)
            | Q(deepzoom__isnull=False)
        )
        .only(
            "id",
            "permissions_id",
            "thumbnail_id",
            "squeezed_datafile_id",
            "deepzoom_id",
            "derived_id",
        )
        .order_by("id")
    )
    last_id = 0
    while True:
        batch = list(rows.filter(id__gt=last_id)[:BATCH_SIZE])
        if not batch:
            break
        last_id = batch[-1].id
        manifests = Manifest.objects.in_bulk(
            [
                pk
                for topography in batch
                for pk in (topography.thumbnail_id, topography.squeezed_datafile_id)
                if pk is not None
            ]
        )
        moved = []
        records = []
        for topography in batch:
            if topography.deepzoom_id is not None:
                folder_id = topography.deepzoom_id
                records.append(("deepzoom", topography.id))
            else:
                folder_id = ManifestSet.objects.create(
                    permissions_id=topography.permissions_id
                ).pk
            for attname, step, filename in (
                ("thumbnail_id", "thumbnail", _thumbnail_filename),
                ("squeezed_datafile_id", "squeezed", lambda m: SQUEEZED_FILENAME),
            ):
                manifest = manifests.get(getattr(topography, attname))
                if manifest is None:
                    continue
                manifest.folder_id = folder_id
                manifest.filename = filename(manifest)
                moved.append(manifest)
                records.append((step, topography.id))
            topography.derived_id = folder_id
        Manifest.objects.bulk_update(moved, ["folder", "filename"])
        Topography._base_manager.bulk_update(batch, ["derived"])
        ProcessingStepRecord.objects.bulk_create(
            [
                ProcessingStepRecord(
                    topography_id=topography_id, name=name, version="1", succeeded=True
                )
                for name, topography_id in records
            ],
            ignore_conflicts=True,
        )


def move_out_of_derived_folder(apps, schema_editor):
    """Back to separate fields: the thumbnail and the squeezed datafile leave the
    folder (their names are left as they are), and folders that are no deep zoom
    folder are deleted once empty."""
    Topography = apps.get_model("manager", "Topography")
    Manifest = apps.get_model("files", "Manifest")
    ManifestSet = apps.get_model("files", "ManifestSet")
    rows = Topography._base_manager.filter(derived__isnull=False)
    Manifest.objects.filter(
        Q(pk__in=rows.values("thumbnail_id")) | Q(pk__in=rows.values("squeezed_datafile_id"))
    ).update(folder=None)
    folders = list(
        rows.filter(deepzoom__isnull=True).values_list("derived_id", flat=True)
    )
    rows.update(derived=None)
    ManifestSet.objects.filter(pk__in=folders, files__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("files", "0012_manifest_manifest_unconfirmed_att_idx"),
        ("manager", "0088_derived_folder_and_kind"),
    ]

    operations = [
        migrations.RunPython(backfill_kind, migrations.RunPython.noop),
        migrations.RunPython(move_into_derived_folder, move_out_of_derived_folder),
    ]
