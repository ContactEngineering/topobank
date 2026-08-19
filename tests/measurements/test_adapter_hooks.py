"""
Tests for the hooks through which an adapter reads metadata out of a file.

The inspection task no longer knows what a value means -- it asks the adapter and
stores what comes back. These tests pin down that the hooks are the ones actually
being used (rather than the model having kept a copy of the logic), and that a kind
which declines a hook degrades instead of raising.
"""

import pytest

from topobank.manager.models import Measurement
from topobank.measurements.adapters import (
    MeasurementAdapter,
    NonuniformLineScanAdapter,
    TopographyMapAdapter,
    UniformLineScanAdapter,
)
from topobank.measurements.schemas import (
    NonuniformLineScanFileInfo,
    UniformLineScanFileInfo,
    UniformLineScanMetadata,
)
from topobank.testing.factories import (
    ManifestFactory,
    SurfaceFactory,
    Topography2DFactory,
)

#: A bare 10x10 matrix, so the metadata it does not carry has to be supplied.
DATAFILE = "10x10.txt"


@pytest.fixture
def surface(db):
    return SurfaceFactory()


def uninspected(surface):
    """
    A measurement that has never been inspected, saved but with no cache.

    `data_source is None` is what marks the next inspection as the first one, and
    the factories cannot be used for this: they set `data_source` and inspect on
    creation, so the first-read path would already be behind us.
    """
    topo = Measurement(
        surface=surface,
        created_by=surface.created_by,
        permissions=surface.permissions,
        name=DATAFILE,
        datafile=ManifestFactory(filename=DATAFILE, permissions=surface.permissions),
        data_source=None,
        metadata={"size_x": 10, "size_y": 10, "unit": "µm"},
    )
    topo.save()
    return topo


#
# read_file_info
#


def test_the_inspection_records_what_the_adapter_reports(surface, mocker):
    """
    The values come from the hook, not from a second copy of the same logic.

    A model that still computed these itself would pass a test that only checked
    the stored numbers, so the hook is stubbed and the store inspected.
    """
    mocker.patch.object(
        TopographyMapAdapter,
        "read_file_info",
        return_value={"undefined_data_fraction": 0.25, "has_undefined_data": True},
    )

    topo = Topography2DFactory(surface=surface)

    assert topo.info.undefined_data_fraction == 0.25
    assert topo.info.has_undefined_data is True


def test_a_kind_that_reports_nothing_leaves_the_rest_of_the_cache_alone(
    surface, mocker
):
    """The default hook returns an empty mapping, which must not blank the cache."""
    mocker.patch.object(TopographyMapAdapter, "read_file_info", return_value={})

    topo = Topography2DFactory(surface=surface)

    assert topo.info.resolution_x == 10
    assert topo.info.undefined_data_fraction is None


def test_the_base_adapter_reports_no_file_info():
    assert MeasurementAdapter.read_file_info(None, None, None) == {}


#
# read_initial_metadata
#


def test_the_adapter_imports_the_instrument_description(surface, mocker):
    """
    ``channel.info["instrument"]`` is a reader convention, so the adapter reads it.

    Injected through the hook rather than through a fixture file that happens to
    carry instrument metadata, so the test says something about the seam and not
    about which test file has what in it.
    """

    def fake_read(self, measurement, channel, metadata):
        metadata.instrument.name = "a microscope"
        metadata.instrument.type = "microscope-based"

    mocker.patch.object(TopographyMapAdapter, "read_initial_metadata", fake_read)
    topo = uninspected(surface)

    topo.refresh_cache()

    assert topo.meta.instrument.name == "a microscope"
    assert topo.meta.instrument.type == "microscope-based"


def test_a_file_without_instrument_information_is_not_an_error(surface):
    """Every lookup in the hook may fail; the type then falls back to undefined."""
    topo = uninspected(surface)

    topo.refresh_cache()

    assert topo.meta.instrument.type == "undefined"


def test_initial_metadata_is_imported_only_on_the_first_read(surface, mocker):
    """
    Re-importing would overwrite metadata the user has since corrected by hand.

    `data_source`, which the first inspection sets, is what tells the two apart.
    """
    topo = uninspected(surface)
    topo.refresh_cache()
    hook = mocker.patch.object(TopographyMapAdapter, "read_initial_metadata")

    topo.refresh_cache()

    hook.assert_not_called()


#
# get_undefined_data_status
#


def test_the_status_comes_from_the_adapter(surface, mocker):
    mocker.patch.object(
        TopographyMapAdapter, "get_undefined_data_status", return_value="a verdict"
    )

    topo = Topography2DFactory(surface=surface)

    assert topo.get_undefined_data_status() == "a verdict"


def test_a_kind_with_no_notion_of_undefined_data_says_nothing():
    """
    The base returns None rather than a string, so a caller can leave the
    statement out instead of printing something untrue about, say, a spectrum.
    """
    assert MeasurementAdapter.get_undefined_data_status(None, None) is None


class _StubMeasurement:
    """
    Just enough of a measurement to ask an adapter about undefined data.

    Deliberately without a `meta`: a kind that cannot fill undefined data must not
    consult its metadata for a fill mode, and the absence here is what proves it.
    Accessing it raises rather than quietly returning a default.
    """

    def __init__(self, info):
        self.info = info


def test_a_nonuniform_line_scan_never_offers_interpolation():
    """
    Non-uniformly spaced points cannot be interpolated, and the schema has no
    fill mode to read. This used to be a `getattr` fallback in the model; it is a
    declared capability now.

    Such a scan still says that no correction is performed -- which is true, and
    was what the fallback produced -- but it can never claim to interpolate.
    """
    assert NonuniformLineScanAdapter.can_fill_undefined_data is False
    measurement = _StubMeasurement(
        NonuniformLineScanFileInfo(has_undefined_data=True, undefined_data_fraction=0.5)
    )

    status = NonuniformLineScanAdapter().get_undefined_data_status(measurement)

    assert "50% of the data points are undefined" in status
    assert "No correction of undefined data is performed" in status
    assert "interpolation" not in status


def test_a_uniform_line_scan_reports_the_fill_mode_it_will_use():
    """The counterpart: a kind that can fill says what it does."""
    assert UniformLineScanAdapter.can_fill_undefined_data is True
    measurement = _StubMeasurement(
        UniformLineScanFileInfo(has_undefined_data=True, undefined_data_fraction=0.5)
    )
    measurement.meta = UniformLineScanMetadata(fill_undefined_data_mode="harmonic")

    status = UniformLineScanAdapter().get_undefined_data_status(measurement)

    assert "harmonic interpolation" in status


def test_the_fill_mode_of_a_kind_that_cannot_fill_is_never_read():
    """
    The helper is what keeps `apply_filters` and the status string from having to
    know that the field may not exist.
    """
    assert "fill_undefined_data_mode" not in (
        NonuniformLineScanAdapter.Metadata.model_fields
    )

    mode = NonuniformLineScanAdapter().fill_undefined_data_mode_of(_StubMeasurement(None))

    assert mode == "do-not-fill"


#
# is_metadata_complete
#


def test_a_measurement_with_no_kind_and_no_file_is_incomplete():
    """
    Nothing can say what such a measurement still needs, so it is not complete.

    No database row involved: the point is that the property answers rather than
    raising.
    """
    assert Measurement(kind=None).is_metadata_complete is False


def test_a_kind_whose_plugin_is_not_installed_is_incomplete():
    assert Measurement(kind="a-kind-from-an-uninstalled-plugin").is_metadata_complete is (
        False
    )


def test_a_stored_document_that_does_not_validate_is_incomplete(caplog):
    """
    A document that does not match its kind is a fault, not missing user input.

    Reporting it as incomplete keeps the inspection from generating artifacts from
    metadata it cannot parse; the log line is what makes the fault findable, so it
    is part of the assertion.
    """
    # `size_y` belongs to a map, and a line scan's schema forbids it.
    measurement = Measurement(
        kind="uniform-line-scan", metadata={"size_x": 1.0, "size_y": 2.0}
    )

    assert measurement.is_metadata_complete is False
    assert "does not validate" in caplog.text
