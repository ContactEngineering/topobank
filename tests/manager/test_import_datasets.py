"""
Tests for the ``import_datasets`` management command.

The command imports a surface from a previously-downloaded container archive
(ONLY FOR USE WITH FILES FROM TRUSTED SOURCES). We build a real archive on disk
with ``export_container_zip`` and import it back, which exercises the full
command path: user lookup, archive parsing, topography creation and property
import.
"""

import os
import tempfile

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from topobank.manager.export_zip import export_container_zip
from topobank.manager.models import Surface
from topobank.testing.factories import (
    PropertyFactory,
    SurfaceFactory,
    Topography2DFactory,
    UserFactory,
)


@pytest.fixture
def container_archive(db):
    """Build a real surface container ZIP on disk and return its path."""
    author = UserFactory()
    surface = SurfaceFactory(created_by=author, name="Source surface")
    topo = Topography2DFactory(surface=surface, size_x=10, size_y=5)
    topo.make_squeezed(save=True)
    PropertyFactory.create(name="material", value="steel", surface=surface)
    PropertyFactory.create(name="thickness", value=2.0, unit="mm", surface=surface)

    handle = tempfile.NamedTemporaryFile(mode="wb", suffix=".zip", delete=False)
    export_container_zip(handle, [surface])
    handle.close()
    yield handle.name
    os.unlink(handle.name)


@pytest.mark.django_db
def test_import_datasets_creates_surface_with_data(container_archive):
    importer = UserFactory(username="importer")

    call_command("import_datasets", "importer", container_archive, "--ignore-missing")

    surfaces = Surface.objects.filter(created_by=importer)
    assert surfaces.count() == 1
    surface = surfaces.get()
    assert surface.topography_set.count() == 1
    # The import records its provenance in the description.
    assert "Imported from file" in surface.description
    # Both the categorical and the numerical property were imported.
    names = set(surface.properties.values_list("name", flat=True))
    assert {"material", "thickness"} <= names


@pytest.mark.django_db
def test_import_datasets_unknown_user_raises():
    with pytest.raises(CommandError):
        call_command("import_datasets", "no-such-user", "/nonexistent.zip")


@pytest.mark.django_db
def test_import_datasets_corrupt_archive_raises():
    UserFactory(username="importer2")
    bad = tempfile.NamedTemporaryFile(mode="w", suffix=".zip", delete=False)
    bad.write("this is not a zip file")
    bad.close()
    try:
        with pytest.raises(CommandError):
            call_command("import_datasets", "importer2", bad.name)
    finally:
        os.unlink(bad.name)
