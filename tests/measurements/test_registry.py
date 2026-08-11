"""
Tests for the measurement-type registry.

The registry is the seam that lets a package outside TopoBank add a kind of
measurement, so what matters here is the contract it offers such a package:
registration is keyed by a stable name, lookup fails loudly for an unknown kind,
and which type claims a data channel is decided by the types themselves.
"""

import pytest

from topobank.measurements.registry import (
    AlreadyRegisteredError,
    MeasurementRegistryError,
    UnknownMeasurementKindError,
    UnsupportedChannelError,
    get_measurement_kinds,
    get_measurement_type,
    get_measurement_types,
    has_measurement_type,
    infer_kind,
    register_measurement_type,
    unregister_measurement_type,
)
from topobank.measurements.types import (
    MeasurementType,
    NonuniformLineScanType,
    TopographyMapType,
    UniformLineScanType,
)


class FakeChannel:
    """The handful of channel attributes the built-in types look at."""

    def __init__(self, dim=2, unit="um", is_uniform=True, name="channel"):
        self.dim = dim
        self.unit = unit
        self.is_uniform = is_uniform
        self.name = name


@pytest.fixture
def registered():
    """Register a throwaway type and remove it again afterwards."""
    registered_names = []

    def register(cls):
        register_measurement_type(cls)
        registered_names.append(cls.Meta.name)
        return cls

    yield register

    for name in registered_names:
        unregister_measurement_type(name)


#
# Registration
#


def test_a_registered_type_is_returned_as_a_singleton(registered):
    @registered
    class Spectrum(MeasurementType):
        class Meta:
            name = "test-singleton"
            display_name = "Test singleton"

        @classmethod
        def claims_channel(cls, channel):
            return False

        def read(self, measurement, **kwargs):
            return None

    # The decorator returns the class, so it stays usable under its own name...
    assert Spectrum.Meta.name == "test-singleton"
    # ...while the registry holds one instance of it, handed out every time.
    assert get_measurement_type("test-singleton") is get_measurement_type(
        "test-singleton"
    )
    assert isinstance(get_measurement_type("test-singleton"), Spectrum)


def test_a_type_without_a_name_is_refused():
    class Nameless(MeasurementType):
        class Meta:
            name = None

        @classmethod
        def claims_channel(cls, channel):
            return False

        def read(self, measurement, **kwargs):
            return None

    with pytest.raises(MeasurementRegistryError, match="does not declare"):
        register_measurement_type(Nameless)


def test_two_types_cannot_claim_the_same_kind(registered):
    @registered
    class First(MeasurementType):
        class Meta:
            name = "test-duplicate"

        @classmethod
        def claims_channel(cls, channel):
            return False

        def read(self, measurement, **kwargs):
            return None

    class Second(MeasurementType):
        class Meta:
            name = "test-duplicate"

        @classmethod
        def claims_channel(cls, channel):
            return False

        def read(self, measurement, **kwargs):
            return None

    with pytest.raises(AlreadyRegisteredError, match="already registered"):
        register_measurement_type(Second)


def test_registering_the_same_class_twice_is_harmless(registered):
    """A module imported through two paths must not blow up at import time."""

    @registered
    class Reimported(MeasurementType):
        class Meta:
            name = "test-reimported"

        @classmethod
        def claims_channel(cls, channel):
            return False

        def read(self, measurement, **kwargs):
            return None

    assert register_measurement_type(Reimported) is Reimported


#
# Lookup
#


def test_an_unknown_kind_names_the_missing_package():
    """
    The message is the whole point of the error.

    It is what an administrator sees when a measurement outlives the plugin that
    created it, so it has to say which kind is missing.
    """
    with pytest.raises(UnknownMeasurementKindError) as excinfo:
        get_measurement_type("no-such-kind")

    assert "no-such-kind" in str(excinfo.value)
    assert "may not be installed" in str(excinfo.value)


def test_absence_can_be_checked_without_catching():
    assert has_measurement_type(TopographyMapType.Meta.name)
    assert not has_measurement_type("no-such-kind")


def test_the_built_in_kinds_are_registered():
    kinds = get_measurement_kinds()

    assert set(kinds) >= {
        "topography-map",
        "uniform-line-scan",
        "nonuniform-line-scan",
    }
    assert set(get_measurement_types()) == set(kinds)


#
# Inferring the kind of a channel
#


@pytest.mark.parametrize(
    "channel,expected",
    [
        (FakeChannel(dim=2), TopographyMapType),
        (FakeChannel(dim=1, is_uniform=True), UniformLineScanType),
        (FakeChannel(dim=1, is_uniform=False), NonuniformLineScanType),
    ],
)
def test_a_height_channel_is_claimed_by_exactly_one_built_in_type(channel, expected):
    assert infer_kind(channel) == expected.Meta.name
    # Exactly one: the others must not claim it, or the result would depend on
    # registration order.
    claiming = [
        measurement_type
        for measurement_type in get_measurement_types().values()
        if measurement_type.claims_channel(channel)
    ]
    assert len(claiming) == 1


def test_a_channel_that_is_not_height_data_is_claimed_by_nobody():
    """
    A tuple unit means the data is not a height (adhesion, current, ...).

    Such channels are listed in a file's inventory but no built-in type can import
    them, which is exactly the gap an external plugin fills.
    """
    channel = FakeChannel(dim=2, unit=("um", "nN"), name="adhesion")

    with pytest.raises(UnsupportedChannelError, match="adhesion"):
        infer_kind(channel)


def test_a_plugin_type_can_claim_a_channel_the_built_ins_reject(registered):
    """The registry must not need editing for a new modality to be importable."""
    channel = FakeChannel(dim=2, unit=("um", "nN"), name="adhesion")

    @registered
    class AdhesionMap(MeasurementType):
        class Meta:
            name = "test-adhesion-map"

        @classmethod
        def claims_channel(cls, other):
            return isinstance(other.unit, tuple) and other.unit[1] == "nN"

        def read(self, measurement, **kwargs):
            return None

    assert infer_kind(channel) == "test-adhesion-map"


def test_a_dimension_no_type_handles_is_rejected():
    with pytest.raises(UnsupportedChannelError):
        infer_kind(FakeChannel(dim=3))
