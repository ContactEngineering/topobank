"""
Tests for the measurement metadata schemas.

These schemas replace typed Django columns, so what matters is that they keep the
guarantees a column gave -- rejecting values the database would have rejected --
and add the one a column could not: a field that does not apply to a kind is
absent rather than null.
"""

import pytest

from topobank.measurements import schemas
from topobank.measurements.schemas import (
    NonuniformLineScanFileInfo,
    NonuniformLineScanMetadata,
    TopographyMapFileInfo,
    TopographyMapMetadata,
    UniformLineScanMetadata,
    coerce_metadata,
    dump_metadata,
    significant_values,
)


#
# What each kind has
#


def test_a_field_that_does_not_apply_to_a_kind_is_absent():
    """
    The point of per-kind schemas.

    A column could only be null for a line scan; here `size_y` does not exist,
    so nothing can read or write it by accident.
    """
    assert "size_y" in TopographyMapMetadata.model_fields
    assert "size_y" not in UniformLineScanMetadata.model_fields


def test_a_nonuniform_line_scan_has_no_periodicity_or_fill_mode():
    """
    Structural, not a runtime flag.

    Periodicity and interpolation are meaningless for non-uniformly spaced
    points; this used to be expressed by clearing `is_periodic_editable`.
    """
    fields = NonuniformLineScanMetadata.model_fields

    assert "is_periodic" not in fields
    assert "fill_undefined_data_mode" not in fields
    # ... and the file-info side agrees that periodicity is never offered.
    assert NonuniformLineScanFileInfo().is_periodic_editable is False


def test_a_value_the_kind_does_not_know_is_rejected_not_stored():
    with pytest.raises(ValueError):
        UniformLineScanMetadata(size_y=1.0)


#
# Validation the columns used to do
#


def test_the_choices_match_the_columns_they_replace():
    """
    The literals have to accept every value already in the database.

    A stored `µm` that the schema spelled `um` would fail the backfill on real
    data and pass every test written against the schema alone.
    """
    from topobank.manager.models import Measurement

    assert list(schemas.LengthUnit.__args__) == [
        value for value, _label in Measurement.LENGTH_UNIT_CHOICES
    ]
    assert list(schemas.DetrendMode.__args__) == [
        value for value, _label in Measurement.DETREND_MODE_CHOICES
    ]
    assert list(schemas.FillUndefinedDataMode.__args__) == [
        value for value, _label in Measurement.FILL_UNDEFINED_DATA_MODE_CHOICES
    ]
    assert list(schemas.InstrumentType.__args__) == [
        value for value, _label in Measurement.INSTRUMENT_TYPE_CHOICES
    ]


def test_a_negative_size_is_rejected():
    """`MinValueValidator(0.0)` on the column becomes `ge=0` here."""
    with pytest.raises(ValueError):
        TopographyMapMetadata(size_x=-1.0)


def test_an_out_of_range_undefined_data_fraction_is_rejected():
    with pytest.raises(ValueError):
        TopographyMapFileInfo(undefined_data_fraction=1.5)


def test_an_unknown_field_is_rejected_rather_than_kept():
    """`extra="forbid"`: a typo must not become a silently stored key."""
    with pytest.raises(ValueError):
        TopographyMapMetadata(size_ex=1.0)


def test_an_invalid_assignment_fails_at_the_write():
    """
    `validate_assignment`, on the nested instrument model too.

    These documents are mutated in place -- `read_initial_metadata` assigns to
    `metadata.instrument.type` -- so a value the schema refuses has to fail at the
    assignment. Without this, it would be accepted silently, stored, and only
    explode on the next *read* of the document, far from the faulty write.
    """
    metadata = TopographyMapMetadata()

    with pytest.raises(ValueError):
        metadata.size_x = -1.0
    with pytest.raises(ValueError):
        metadata.instrument.type = "not-an-instrument-type"


#
# Completeness
#


def test_metadata_is_incomplete_until_size_and_unit_are_known():
    assert TopographyMapMetadata().missing_metadata() == ["physical size", "unit"]
    assert not TopographyMapMetadata().is_complete()

    complete = TopographyMapMetadata(size_x=1.0, size_y=2.0, unit="µm")

    assert complete.missing_metadata() == []
    assert complete.is_complete()


def test_a_map_without_size_y_is_incomplete():
    """A map needs both lateral sizes; a line scan needs only one."""
    assert not TopographyMapMetadata(size_x=1.0, unit="µm").is_complete()
    assert UniformLineScanMetadata(size_x=1.0, unit="µm").is_complete()


#
# Round-tripping and change detection
#


def test_metadata_survives_a_dump_and_reload():
    """
    Storage is a JSON column, so anything dumped has to parse back.

    `exclude_none` matters here: `InstrumentParametersModel` declares its fields
    non-optional while defaulting them to None, so a document written with
    explicit nulls could not be re-read.
    """
    original = TopographyMapMetadata(size_x=1.0, size_y=2.0, unit="nm")

    reloaded = TopographyMapMetadata(**dump_metadata(original))

    assert reloaded == original


def test_significance_is_declared_per_field_and_opt_out():
    """
    Where "significant" is specified, and what the default is.

    A field is significant unless it is built with `_insignificant(...)`, which is
    the safe direction to default in: forgetting the marker means a change
    invalidates derived data unnecessarily, while an opt-in scheme would silently
    fail to invalidate it. Everything physical is therefore significant without
    having to say so, and the exceptions are visible in the schema.
    """
    values = significant_values(
        TopographyMapMetadata(size_x=1.0, size_y=2.0, unit="µm")
    )

    assert {"size_x", "size_y", "unit", "height_scale", "detrend_mode"} <= set(values)
    # The one declared exception, and it is nested.
    assert "type" in values["instrument"]
    assert "name" not in values["instrument"]


def test_the_instrument_name_does_not_count_as_a_change():
    """
    Significance drives cache invalidation.

    Renaming an instrument must not invalidate thumbnails and analyses, while
    changing its type must.
    """
    before = TopographyMapMetadata(size_x=1.0, size_y=2.0, unit="µm")
    renamed = before.model_copy(deep=True)
    renamed.instrument.name = "a different label"
    retyped = before.model_copy(deep=True)
    retyped.instrument.type = "contact-based"

    assert significant_values(renamed) == significant_values(before)
    assert significant_values(retyped) != significant_values(before)


def test_changing_a_physical_field_counts_as_a_change():
    before = TopographyMapMetadata(size_x=1.0, size_y=2.0, unit="µm")
    after = before.model_copy(update={"size_x": 2.0})

    assert significant_values(after) != significant_values(before)


#
# Changing kind
#


def test_coercing_to_another_kind_keeps_what_still_applies():
    """
    Selecting a channel of a different dimensionality changes the kind.

    Metadata the user adjusted by hand should survive wherever the new kind has
    somewhere to put it.
    """
    a_map = TopographyMapMetadata(
        size_x=1.0, size_y=2.0, unit="nm", detrend_mode="height"
    )

    line_scan = coerce_metadata(UniformLineScanMetadata, dump_metadata(a_map))

    assert line_scan.kind == "uniform-line-scan"
    assert line_scan.size_x == 1.0
    assert line_scan.unit == "nm"
    assert line_scan.detrend_mode == "height"


def test_coercing_drops_what_the_new_kind_cannot_hold():
    a_map = TopographyMapMetadata(size_x=1.0, size_y=2.0, unit="nm")

    line_scan = coerce_metadata(UniformLineScanMetadata, dump_metadata(a_map))

    assert "size_y" not in dump_metadata(line_scan)


def test_coercing_a_rejected_value_falls_back_to_the_default():
    """A value the target schema refuses must not abort the whole conversion."""
    coerced = coerce_metadata(
        UniformLineScanMetadata,
        {"kind": "topography-map", "size_x": 1.0, "detrend_mode": "not-a-mode"},
    )

    assert coerced.size_x == 1.0
    assert coerced.detrend_mode == "center"
