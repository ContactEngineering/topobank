"""
Tests for the metadata backfill in `manager.0090`.

The migration reshapes every measurement in the database, so what matters is not
only that it copies the right values but that what it produces actually parses as
the schema for that kind. A document the schemas reject would leave the
measurement unreadable, and nothing else in the suite would notice: the columns
are still there and the code that reads them is gone.
"""

import importlib

import pytest

from topobank.manager.models import Measurement
from topobank.measurements.schemas import (
    TopographyMapFileInfo,
    TopographyMapMetadata,
)
from topobank.testing.factories import Topography1DFactory, Topography2DFactory

# The module name starts with a digit, so it cannot be imported with `from ...
# import`.
backfill_module = importlib.import_module(
    "topobank.manager.migrations.0090_backfill_measurement_metadata"
)

#: The pre-`0091` names the migration knows the columns by, mapped to the current
#: ones. `0090` runs before the rename, so it addresses them the old way.
HISTORICAL_NAMES = {
    "instrument_name": "legacy_instrument_name",
    "instrument_type": "legacy_instrument_type",
    "instrument_parameters": "legacy_instrument_parameters",
    **{
        name: f"legacy_{name}"
        for name in (
            "size_x", "size_y", "unit", "height_scale", "detrend_mode",
            "is_periodic", "fill_undefined_data_mode", "resolution_x",
            "resolution_y", "bandwidth_lower", "bandwidth_upper",
            "short_reliability_cutoff", "has_undefined_data",
            "undefined_data_fraction", "detrend_parameters", "size_editable",
            "unit_editable", "height_scale_editable", "is_periodic_editable",
        )
    },
}


class _HistoricalMeasurement:
    """Presents the pre-`0091` field names to the migration under test."""

    def __init__(self, measurement):
        self._measurement = measurement

    def __getattr__(self, name):
        return getattr(self._measurement, HISTORICAL_NAMES.get(name, name))

    def __setattr__(self, name, value):
        if name == "_measurement":
            super().__setattr__(name, value)
        else:
            setattr(self._measurement, name, value)


def run_backfill(measurement):
    """Run the migration's per-row work against one real measurement."""
    kind = measurement.kind
    metadata_fields, file_info_fields = backfill_module.SHAPES[kind]
    historical = _HistoricalMeasurement(measurement)

    metadata = backfill_module.document(historical, kind, metadata_fields)
    metadata["instrument"] = backfill_module.instrument_document(historical)
    file_info = backfill_module.document(historical, kind, file_info_fields)
    return metadata, file_info


def seed_legacy_columns(measurement, **values):
    """Write the pre-migration columns, as a database from before `0089` had."""
    Measurement.objects.filter(pk=measurement.pk).update(
        **{f"legacy_{name}": value for name, value in values.items()}
    )
    measurement.refresh_from_db()


@pytest.mark.django_db
def test_the_backfill_produces_documents_the_schemas_accept():
    """
    The check that the rules alone cannot give.

    A document with a stray key, or a value the schema rejects, would make the
    measurement unreadable after `0091` removes every other way of getting at it.
    """
    measurement = Topography2DFactory()
    seed_legacy_columns(
        measurement,
        size_x=10.0,
        size_y=5.0,
        unit="µm",
        height_scale=2.0,
        detrend_mode="height",
        is_periodic=True,
        fill_undefined_data_mode="harmonic",
        instrument_name="A profilometer",
        instrument_type="contact-based",
        instrument_parameters={"tip_radius": {"value": 10, "unit": "nm"}},
        resolution_x=256,
        resolution_y=128,
        has_undefined_data=True,
        undefined_data_fraction=0.25,
        size_editable=True,
    )

    metadata, file_info = run_backfill(measurement)

    # Parsing is the assertion: `extra="forbid"` rejects a stray key and the
    # literals reject an unknown value.
    parsed = TopographyMapMetadata(**metadata)
    assert parsed.size_x == 10.0
    assert parsed.size_y == 5.0
    assert parsed.unit == "µm"
    assert parsed.detrend_mode == "height"
    assert parsed.is_periodic is True
    assert parsed.instrument.name == "A profilometer"
    assert parsed.instrument.type == "contact-based"

    parsed_info = TopographyMapFileInfo(**file_info)
    assert parsed_info.resolution_x == 256
    assert parsed_info.resolution_y == 128
    assert parsed_info.undefined_data_fraction == 0.25
    assert parsed_info.size_editable is True


@pytest.mark.django_db
def test_a_line_scan_gets_no_map_only_fields():
    """`size_y` and `resolution_y` have nowhere to go on a line scan."""
    measurement = Topography1DFactory()
    Measurement.objects.filter(pk=measurement.pk).update(kind="uniform-line-scan")
    measurement.refresh_from_db()
    seed_legacy_columns(measurement, size_x=9.0, size_y=5.0, resolution_y=128)

    metadata, file_info = run_backfill(measurement)

    assert "size_y" not in metadata
    assert "resolution_y" not in file_info


@pytest.mark.django_db
def test_a_nonuniform_line_scan_drops_periodicity_and_filling():
    """
    Neither applies to non-uniformly spaced points.

    `is_periodic` was forced to False on inspection anyway, and the fill mode was
    never applied, so nothing is lost by having nowhere to put them.
    """
    measurement = Topography1DFactory()
    Measurement.objects.filter(pk=measurement.pk).update(kind="nonuniform-line-scan")
    measurement.refresh_from_db()
    seed_legacy_columns(
        measurement, size_x=9.0, is_periodic=False, fill_undefined_data_mode="harmonic"
    )

    metadata, _ = run_backfill(measurement)

    assert "is_periodic" not in metadata
    assert "fill_undefined_data_mode" not in metadata


@pytest.mark.django_db
def test_a_null_column_is_omitted_rather_than_written_as_null():
    """
    `exclude_none` on the way out has a counterpart on the way in.

    `InstrumentParametersModel` rejects an explicit None for fields it defaults to
    None, so a document that wrote them out could not be read back.
    """
    measurement = Topography2DFactory()
    seed_legacy_columns(measurement, size_x=10.0, size_y=5.0, unit="µm")
    Measurement.objects.filter(pk=measurement.pk).update(
        legacy_bandwidth_lower=None, legacy_short_reliability_cutoff=None
    )
    measurement.refresh_from_db()

    _, file_info = run_backfill(measurement)

    assert "bandwidth_lower" not in file_info
    assert "short_reliability_cutoff" not in file_info
