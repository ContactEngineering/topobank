"""
Exporting a container and importing it again.

The round trip is what keeps published datasets usable, so it has to preserve the
kind, the metadata and - crucially - which data channel a measurement refers to.
"""

import tempfile
import zipfile

import pytest

from topobank.manager.export_zip import export_container_zip
from topobank.manager.import_zip import import_container_zip
from topobank.testing.factories import (
    ManifestFactory,
    SurfaceFactory,
    TopographyMapFactory,
    UserFactory,
)


def roundtrip(surfaces, user):
    """Export `surfaces` and import the archive again, returning the new surfaces."""
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".zip") as outfile:
        export_container_zip(outfile, surfaces)
        outfile.flush()
        with zipfile.ZipFile(outfile.name, mode="r") as zf:
            return import_container_zip(zf, user)


@pytest.mark.django_db
def test_kind_and_metadata_survive_a_round_trip():
    user = UserFactory()
    surface = SurfaceFactory(created_by=user)
    original = TopographyMapFactory(
        surface=surface,
        size_x=10.0,
        size_y=5.0,
        unit="µm",
        detrend_mode="height",
        is_periodic=True,
        instrument_name="My profilometer",
        instrument_type="contact-based",
        instrument_parameters={"tip_radius": {"value": 10, "unit": "µm"}},
    )
    original.make_squeezed(save=True)

    (imported_surface,) = roundtrip([surface], user)
    (imported,) = imported_surface.measurements.all()

    # The kind is carried explicitly, so it is known before the file is read.
    assert imported.kind == original.kind
    assert imported.channel_name == original.channel_name

    imported.refresh_cache()
    assert imported.kind == original.kind
    assert imported.meta.size_x == original.meta.size_x
    assert imported.meta.size_y == original.meta.size_y
    assert imported.meta.unit == original.meta.unit
    assert imported.meta.detrend_mode == "height"
    assert imported.meta.is_periodic
    assert imported.meta.instrument.name == "My profilometer"
    assert imported.meta.instrument.type == "contact-based"


@pytest.mark.django_db
def test_selected_channel_survives_a_round_trip():
    """
    A measurement on a non-default channel must come back on the same channel.

    ``example3.di`` has four channels and its default is not the one selected here,
    so an export that dropped the channel identity would silently produce a
    different measurement on import.
    """
    from topobank.manager.models import Measurement

    user = UserFactory()
    surface = SurfaceFactory(created_by=user)
    datafile = ManifestFactory(
        filename="example3.di", permissions=surface.permissions
    )
    original = Measurement(
        surface=surface,
        created_by=user,
        permissions=surface.permissions,
        name="example3.di",
        datafile=datafile,
        channel_name="Height",  # not the default channel
    )
    original.save()
    original.refresh_cache()
    assert original.channel_name == "Height"
    heights = original.read().heights()

    (imported_surface,) = roundtrip([surface], user)
    (imported,) = imported_surface.measurements.all()

    assert imported.channel_name == "Height"
    imported.refresh_cache()
    assert imported.channel_name == "Height"
    # Same channel means the same data.
    assert imported.read().heights().shape == heights.shape


@pytest.mark.django_db
def test_nonuniform_line_scan_survives_a_round_trip():
    """
    The kind with the smallest metadata schema.

    Its metadata has no periodicity and no fill mode at all, so a round trip must
    not reintroduce them.
    """
    from topobank.testing.factories import NonuniformLineScanFactory

    user = UserFactory()
    surface = SurfaceFactory(created_by=user)
    original = NonuniformLineScanFactory(surface=surface, size_x=9.0, unit="nm")
    original.make_squeezed(save=True)

    (imported_surface,) = roundtrip([surface], user)
    (imported,) = imported_surface.measurements.all()
    imported.refresh_cache()

    assert imported.kind == "nonuniform-line-scan"
    assert "is_periodic" not in imported.metadata
    assert "fill_undefined_data_mode" not in imported.metadata
    assert imported.meta.size_x == original.meta.size_x
