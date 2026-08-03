"""
Tests for how much of a measurement is undefined.

A measurement can carry data points that hold no value, because the instrument
could not resolve them. `Topography.has_undefined_data` records that this is the
case and `Topography.undefined_data_fraction` how much of the data it affects,
both describing the data as measured rather than as filtered for display.
"""

import pytest

from topobank.manager.models import Topography
from topobank.testing.factories import ManifestFactory, SurfaceFactory

# A bare 10x10 matrix of numbers with seven of its hundred entries written as
# `nan`; the text reader turns those into a masked array. Its counterpart without
# undefined data is the file the 2D factory uses by default.
UNDEFINED_DATAFILE = "10x10_undefined.txt"
DEFINED_DATAFILE = "10x10.txt"
UNDEFINED_POINTS = 7
TOTAL_POINTS = 100


def _make_topography(surface, filename, **kwargs):
    """Create and inspect a measurement backed by the given fixture file."""
    datafile = ManifestFactory(filename=filename, permissions=surface.permissions)
    topo = Topography(
        surface=surface,
        created_by=surface.created_by,
        permissions=surface.permissions,
        name=filename,
        datafile=datafile,
        data_source=0,
        # The file is a bare matrix, so the metadata it does not carry has to be
        # supplied for the measurement to be processed at all.
        size_x=10,
        size_y=10,
        unit="µm",
        height_scale=1,
        **kwargs,
    )
    topo.save()
    topo.refresh_cache()
    return topo


@pytest.fixture
def surface(db):
    return SurfaceFactory()


def test_reports_the_fraction_of_undefined_points(surface):
    topo = _make_topography(surface, UNDEFINED_DATAFILE)
    assert topo.has_undefined_data is True
    assert topo.undefined_data_fraction == pytest.approx(UNDEFINED_POINTS / TOTAL_POINTS)


def test_reports_zero_for_a_complete_measurement(surface):
    topo = _make_topography(surface, DEFINED_DATAFILE)
    assert topo.has_undefined_data is False
    assert topo.undefined_data_fraction == 0


def test_reports_the_measured_data_even_when_filling_is_enabled(surface):
    """Filling replaces the undefined points, and the filtered topography reports
    no undefined data by definition. The stored values describe the measurement,
    so they must not be erased by the user's choice to interpolate."""
    topo = _make_topography(
        surface,
        UNDEFINED_DATAFILE,
        fill_undefined_data_mode=Topography.FILL_UNDEFINED_DATA_MODE_HARMONIC,
    )
    assert topo.has_undefined_data is True
    assert topo.undefined_data_fraction == pytest.approx(UNDEFINED_POINTS / TOTAL_POINTS)


def test_fraction_is_unknown_before_inspection(surface):
    datafile = ManifestFactory(
        filename=UNDEFINED_DATAFILE, permissions=surface.permissions
    )
    topo = Topography(
        surface=surface,
        created_by=surface.created_by,
        permissions=surface.permissions,
        name=UNDEFINED_DATAFILE,
        datafile=datafile,
        data_source=None,
    )
    topo.save()
    assert topo.has_undefined_data is None
    assert topo.undefined_data_fraction is None


def test_status_names_the_percentage(surface):
    topo = _make_topography(surface, UNDEFINED_DATAFILE)
    status = topo.get_undefined_data_status()
    assert "7% of the data points are undefined" in status


def test_status_of_a_complete_measurement_names_no_percentage(surface):
    topo = _make_topography(surface, DEFINED_DATAFILE)
    assert "undefined" in topo.get_undefined_data_status()
    assert "% of the data points" not in topo.get_undefined_data_status()


def test_fraction_is_exported_with_the_metadata(surface):
    topo = _make_topography(surface, UNDEFINED_DATAFILE)
    assert topo.to_dict()["undefined_data_fraction"] == pytest.approx(
        UNDEFINED_POINTS / TOTAL_POINTS
    )
