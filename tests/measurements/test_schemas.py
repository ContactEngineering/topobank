"""
Metadata schemas.

The pydantic schemas took over the role the typed Django columns used to play, so
these tests cover what the columns used to guarantee: which fields exist per kind,
which values are accepted, and that a stored document round-trips.
"""

import pydantic
import pytest

from topobank.measurements.schemas import (
    NonuniformLineScanFileInfo,
    NonuniformLineScanMetadata,
    TopographyMapMetadata,
    UniformLineScanMetadata,
    coerce_metadata,
    dump_metadata,
    significant_values,
)


class TestPerKindFields:
    """
    Each kind has exactly the fields that apply to it.

    This is the structural half of the change: what used to be enforced at
    runtime by ``*_editable`` flags and nullable columns is now expressed by the
    schema simply not having the field.
    """

    def test_map_has_two_lateral_sizes(self):
        metadata = TopographyMapMetadata(size_x=1.0, size_y=2.0)
        assert (metadata.size_x, metadata.size_y) == (1.0, 2.0)

    def test_line_scans_have_no_second_size(self):
        for schema in (UniformLineScanMetadata, NonuniformLineScanMetadata):
            assert "size_y" not in schema.model_fields
            with pytest.raises(pydantic.ValidationError):
                schema(size_y=2.0)

    def test_nonuniform_supports_neither_periodicity_nor_filling(self):
        """A nonuniform line scan supports neither, so it cannot carry them."""
        assert "is_periodic" not in NonuniformLineScanMetadata.model_fields
        assert (
            "fill_undefined_data_mode" not in NonuniformLineScanMetadata.model_fields
        )
        with pytest.raises(pydantic.ValidationError):
            NonuniformLineScanMetadata(is_periodic=True)
        with pytest.raises(pydantic.ValidationError):
            NonuniformLineScanMetadata(fill_undefined_data_mode="harmonic")

    def test_uniform_kinds_do_support_them(self):
        for schema in (TopographyMapMetadata, UniformLineScanMetadata):
            metadata = schema(is_periodic=True, fill_undefined_data_mode="harmonic")
            assert metadata.is_periodic
            assert metadata.fill_undefined_data_mode == "harmonic"

    def test_nonuniform_file_info_is_never_periodic_editable(self):
        assert NonuniformLineScanFileInfo().is_periodic_editable is False

    def test_unknown_field_is_rejected(self):
        with pytest.raises(pydantic.ValidationError):
            UniformLineScanMetadata(bogus=1)

    def test_kind_discriminator_is_pinned(self):
        assert TopographyMapMetadata().kind == "topography-map"
        with pytest.raises(pydantic.ValidationError):
            TopographyMapMetadata(kind="uniform-line-scan")


class TestValidation:
    """Validation the Django columns used to provide."""

    def test_negative_size_is_rejected(self):
        with pytest.raises(pydantic.ValidationError):
            UniformLineScanMetadata(size_x=-1.0)

    def test_unit_must_be_a_known_length_unit(self):
        assert UniformLineScanMetadata(unit="µm").unit == "µm"
        with pytest.raises(pydantic.ValidationError):
            UniformLineScanMetadata(unit="furlong")

    def test_detrend_mode_must_be_known(self):
        with pytest.raises(pydantic.ValidationError):
            UniformLineScanMetadata(detrend_mode="sideways")

    def test_assignment_is_validated(self):
        metadata = UniformLineScanMetadata()
        with pytest.raises(pydantic.ValidationError):
            metadata.unit = "furlong"


class TestCompleteness:
    def test_size_and_unit_are_required_to_read_a_file(self):
        metadata = UniformLineScanMetadata()
        assert not metadata.is_complete()
        assert "physical size" in metadata.missing_metadata()
        assert "unit" in metadata.missing_metadata()

    def test_complete_line_scan(self):
        assert UniformLineScanMetadata(size_x=1.0, unit="nm").is_complete()

    def test_a_map_also_needs_its_second_size(self):
        metadata = TopographyMapMetadata(size_x=1.0, unit="nm")
        assert not metadata.is_complete()
        assert metadata.missing_metadata() == ["physical size"]
        assert TopographyMapMetadata(size_x=1.0, size_y=2.0, unit="nm").is_complete()


class TestRoundTrip:
    def test_dump_reloads(self):
        metadata = TopographyMapMetadata(
            size_x=1.0,
            size_y=2.0,
            unit="nm",
            instrument={
                "name": "My AFM",
                "type": "contact-based",
                "parameters": {"tip_radius": {"value": 10, "unit": "nm"}},
            },
        )
        reloaded = TopographyMapMetadata(**dump_metadata(metadata))
        assert reloaded == metadata

    def test_dump_omits_nones(self):
        """
        Required for the round trip, not just for tidiness.

        ``InstrumentParametersModel`` (from SurfaceTopography) declares its fields
        as non-optional with a None default, so it rejects an explicit null on the
        way back in.
        """
        document = dump_metadata(UniformLineScanMetadata())
        assert "size_x" not in document
        assert document["instrument"]["parameters"] == {}
        assert UniformLineScanMetadata(**document) == UniformLineScanMetadata()


class TestSignificantValues:
    """
    Which metadata changes invalidate derived data.

    The model compares these to decide whether to re-run the inspection, so a
    purely descriptive field must not appear.
    """

    def test_instrument_name_is_not_significant(self):
        a = UniformLineScanMetadata(size_x=1.0, unit="nm")
        b = UniformLineScanMetadata(
            size_x=1.0, unit="nm", instrument={"name": "renamed"}
        )
        assert significant_values(a) == significant_values(b)

    def test_size_is_significant(self):
        a = UniformLineScanMetadata(size_x=1.0, unit="nm")
        b = UniformLineScanMetadata(size_x=2.0, unit="nm")
        assert significant_values(a) != significant_values(b)

    def test_instrument_parameters_are_significant(self):
        a = UniformLineScanMetadata(
            instrument={"parameters": {"tip_radius": {"value": 1, "unit": "nm"}}}
        )
        b = UniformLineScanMetadata(
            instrument={"parameters": {"tip_radius": {"value": 2, "unit": "nm"}}}
        )
        assert significant_values(a) != significant_values(b)


class TestCoerceMetadata:
    """
    Carrying metadata across a change of kind.

    Selecting a channel of different dimensionality changes a measurement's kind;
    whatever the new kind also has should survive.
    """

    def test_shared_fields_are_kept(self):
        stored = dump_metadata(
            TopographyMapMetadata(size_x=1.0, size_y=2.0, unit="nm", detrend_mode="height")
        )
        coerced = coerce_metadata(UniformLineScanMetadata, stored)
        assert coerced.size_x == 1.0
        assert coerced.unit == "nm"
        assert coerced.detrend_mode == "height"

    def test_inapplicable_fields_are_dropped(self):
        stored = dump_metadata(TopographyMapMetadata(size_x=1.0, size_y=2.0))
        # A line scan has no size_y at all, so it is dropped rather than failing.
        coerced = coerce_metadata(UniformLineScanMetadata, stored)
        assert coerced.size_x == 1.0
        assert not hasattr(coerced, "size_y")

    def test_periodicity_is_dropped_for_nonuniform(self):
        stored = dump_metadata(
            UniformLineScanMetadata(size_x=1.0, is_periodic=True, unit="nm")
        )
        coerced = coerce_metadata(NonuniformLineScanMetadata, stored)
        assert coerced.size_x == 1.0
        assert not hasattr(coerced, "is_periodic")

    def test_unacceptable_value_falls_back_to_the_default(self):
        """A stored value the target schema rejects must not break the coercion."""
        coerced = coerce_metadata(
            UniformLineScanMetadata, {"unit": "furlong", "size_x": 3.0}
        )
        assert coerced.unit is None
        assert coerced.size_x == 3.0

    def test_empty_metadata_gives_defaults(self):
        assert coerce_metadata(UniformLineScanMetadata, None) == UniformLineScanMetadata()
