"""The measurement type registry."""

import pytest

from topobank.measurements.registry import (
    AlreadyRegisteredError,
    MeasurementRegistryError,
    UnknownMeasurementKindError,
    get_measurement_kinds,
    get_measurement_type,
    get_measurement_types,
    has_measurement_type,
    register_measurement_type,
    unregister_measurement_type,
)
from topobank.measurements.types import (
    MeasurementType,
    NonuniformLineScanType,
    TopographyMapType,
    UniformLineScanType,
)

BUILTIN_KINDS = {
    "topography-map",
    "uniform-line-scan",
    "nonuniform-line-scan",
}


def test_builtin_types_are_registered():
    assert BUILTIN_KINDS <= set(get_measurement_kinds())


@pytest.mark.parametrize(
    "kind,expected_class",
    [
        ("topography-map", TopographyMapType),
        ("uniform-line-scan", UniformLineScanType),
        ("nonuniform-line-scan", NonuniformLineScanType),
    ],
)
def test_lookup_returns_the_singleton_for_a_kind(kind, expected_class):
    measurement_type = get_measurement_type(kind)
    assert isinstance(measurement_type, expected_class)
    # Registry holds one instance per kind, so lookups are stable.
    assert get_measurement_type(kind) is measurement_type


def test_the_three_height_kinds_have_distinct_schemas():
    """
    The whole point of splitting the kinds: they no longer share one descriptor.
    """
    schemas = {
        get_measurement_type(kind).Metadata for kind in sorted(BUILTIN_KINDS)
    }
    assert len(schemas) == 3


def test_unknown_kind_raises():
    with pytest.raises(UnknownMeasurementKindError) as excinfo:
        get_measurement_type("xps-spectrum")
    # The message points at the likely cause: a plugin that is not installed.
    assert "not be installed" in str(excinfo.value)
    assert not has_measurement_type("xps-spectrum")


def test_registering_requires_a_name():
    class Nameless(MeasurementType):
        class Meta:
            name = None

        def read(self, measurement, **kwargs):
            raise NotImplementedError

        def inspect(self, measurement, inspection, channel_index):
            raise NotImplementedError

    with pytest.raises(MeasurementRegistryError, match="Meta.name"):
        register_measurement_type(Nameless)


def test_registering_a_duplicate_kind_raises():
    with pytest.raises(AlreadyRegisteredError, match="topography-map"):

        @register_measurement_type
        class Clashing(TopographyMapType):
            class Meta:
                name = "topography-map"
                display_name = "Something else"


def test_registering_the_same_class_twice_is_harmless():
    """Can happen when a module is imported through two different paths."""
    assert register_measurement_type(TopographyMapType) is TopographyMapType


class TestPluginType:
    """A measurement type from outside the core, e.g. for a spectrum."""

    KIND = "test-spectrum"

    @pytest.fixture
    def plugin_type(self):
        @register_measurement_type
        class SpectrumType(MeasurementType):
            class Meta:
                name = TestPluginType.KIND
                display_name = "Test spectrum"

            def read(self, measurement, **kwargs):
                return "spectrum data"

            def inspect(self, measurement, inspection, channel_index):
                raise NotImplementedError

        yield SpectrumType
        unregister_measurement_type(TestPluginType.KIND)

    def test_plugin_kind_is_available(self, plugin_type):
        assert has_measurement_type(self.KIND)
        assert self.KIND in get_measurement_kinds()
        assert isinstance(get_measurement_type(self.KIND), plugin_type)

    def test_plugin_kind_does_not_yield_surface_topography(self, plugin_type):
        """
        A registered kind need not be topography data at all.

        Anything that iterates measurements as `SurfaceTopography` objects keys
        off this flag rather than assuming.
        """
        assert not get_measurement_type(self.KIND).yields_surface_topography
        assert get_measurement_type("topography-map").yields_surface_topography

    def test_unregistering_removes_the_kind(self, plugin_type):
        unregister_measurement_type(self.KIND)
        assert not has_measurement_type(self.KIND)
        with pytest.raises(UnknownMeasurementKindError):
            get_measurement_type(self.KIND)

    def test_get_measurement_types_is_a_copy(self, plugin_type):
        types = get_measurement_types()
        types.clear()
        assert has_measurement_type(self.KIND)
