"""The data migration that moves derived files into the `derived` folder
(`manager/0089_backfill_derived_folder_and_kind`), run on legacy rows."""

import importlib

import pytest
from django.apps import apps

from topobank.files.models import Manifest
from topobank.manager.models import Topography
from topobank.testing.factories import Topography1DFactory, Topography2DFactory

migration = importlib.import_module(
    "topobank.manager.migrations.0089_backfill_derived_folder_and_kind"
)


def _make_legacy(topo):
    """Back to the state before the migration: thumbnail and squeezed file
    outside any folder, under their old names, the deep zoom folder on its own,
    no derived folder, no kind, no step records."""
    Manifest.objects.filter(pk=topo.thumbnail_id).update(
        folder=None, filename="thumbnail.jpeg"
    )
    Manifest.objects.filter(pk=topo.squeezed_datafile_id).update(
        folder=None, filename=f"{topo.name}-squeezed.nc"
    )
    Topography.objects.filter(pk=topo.pk).update(derived=None, kind=None)
    topo.processing_steps.all().delete()
    return Topography.objects.get(pk=topo.pk)


@pytest.mark.django_db
def test_a_map_gets_its_deep_zoom_folder_as_derived_folder():
    topo = _make_legacy(Topography2DFactory(size_x=1, size_y=1))
    ids = topo.thumbnail_id, topo.squeezed_datafile_id, topo.deepzoom_id
    keys = {m.file.name for m in Manifest.objects.filter(pk__in=ids[:2])}

    migration.backfill_kind(apps, None)
    migration.move_into_derived_folder(apps, None)

    topo = Topography.objects.get(pk=topo.pk)
    assert (topo.thumbnail_id, topo.squeezed_datafile_id, topo.deepzoom_id) == ids
    assert topo.derived_id == topo.deepzoom_id
    assert topo.thumbnail.folder_id == topo.derived_id
    assert topo.squeezed_datafile.filename == "squeezed.nc"
    # Nothing was copied in storage
    assert {topo.thumbnail.file.name, topo.squeezed_datafile.file.name} == keys
    assert topo.kind == "topography-map"
    assert sorted(topo.processing_steps.values_list("name", "version")) == [
        ("deepzoom", "1"),
        ("squeezed", "1"),
        ("thumbnail", "1"),
    ]
    # The deprecated fields are found again by a refresh
    topo.refresh_cache()
    assert Topography.objects.get(pk=topo.pk).deepzoom_id is not None


@pytest.mark.django_db
def test_a_line_scan_gets_a_new_derived_folder():
    topo = _make_legacy(Topography1DFactory())
    assert topo.deepzoom_id is None

    migration.backfill_kind(apps, None)
    migration.move_into_derived_folder(apps, None)

    topo = Topography.objects.get(pk=topo.pk)
    assert sorted(topo.derived.files.values_list("filename", flat=True)) == [
        "squeezed.nc",
        "thumbnail.jpeg",
    ]
    assert topo.deepzoom_id is None
    # The fixture is a nonuniform line scan, whose periodicity is not editable
    assert topo.kind == "nonuniform-line-scan"


@pytest.mark.django_db
def test_the_migration_can_be_reversed():
    topo = _make_legacy(Topography1DFactory())
    migration.move_into_derived_folder(apps, None)

    migration.move_out_of_derived_folder(apps, None)

    topo = Topography.objects.get(pk=topo.pk)
    assert topo.derived_id is None
    assert topo.thumbnail.folder_id is None
    assert topo.squeezed_datafile.folder_id is None


@pytest.mark.django_db
def test_an_uninspected_measurement_keeps_no_kind():
    topo = Topography2DFactory(size_x=1, size_y=1)
    Topography.objects.filter(pk=topo.pk).update(kind=None, resolution_x=None)

    migration.backfill_kind(apps, None)

    assert Topography.objects.get(pk=topo.pk).kind is None
