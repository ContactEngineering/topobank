"""
Tests for the measurement-adapter registry.

The registry is the seam that lets a package outside TopoBank add a kind of
measurement, so what matters here is the contract it offers such a package:
registration is keyed by a stable name, lookup fails loudly for an unknown kind,
and which adapter claims a data channel is decided by the adapters themselves.
"""

import pytest

from topobank.measurements.registry import (
    AlreadyRegisteredError,
    MeasurementRegistryError,
    UnknownMeasurementKindError,
    UnsupportedChannelError,
    get_kinds,
    get_adapter,
    get_adapters,
    has_adapter,
    infer_kind,
    register_adapter,
    unregister_adapter,
)
from topobank.measurements.adapters import (
    MeasurementAdapter,
    NonuniformLineScanAdapter,
    TopographyMapAdapter,
    UniformLineScanAdapter,
)


class FakeChannel:
    """The handful of channel attributes the built-in adapters look at."""

    def __init__(self, dim=2, unit="um", is_uniform=True, name="channel"):
        self.dim = dim
        self.unit = unit
        self.is_uniform = is_uniform
        self.name = name


@pytest.fixture
def registered():
    """Register a throwaway adapter and remove it again afterwards."""
    registered_kinds = []

    def register(cls):
        register_adapter(cls)
        registered_kinds.append(cls.Meta.name)
        return cls

    yield register

    for kind in registered_kinds:
        unregister_adapter(kind)


#
# Registration
#


def test_a_registered_type_is_returned_as_a_singleton(registered):
    @registered
    class Spectrum(MeasurementAdapter):
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
    assert get_adapter("test-singleton") is get_adapter(
        "test-singleton"
    )
    assert isinstance(get_adapter("test-singleton"), Spectrum)


def test_a_type_without_a_name_is_refused():
    class Nameless(MeasurementAdapter):
        class Meta:
            name = None

        @classmethod
        def claims_channel(cls, channel):
            return False

        def read(self, measurement, **kwargs):
            return None

    with pytest.raises(MeasurementRegistryError, match="does not declare"):
        register_adapter(Nameless)


def test_two_types_cannot_claim_the_same_kind(registered):
    @registered
    class First(MeasurementAdapter):
        class Meta:
            name = "test-duplicate"

        @classmethod
        def claims_channel(cls, channel):
            return False

        def read(self, measurement, **kwargs):
            return None

    class Second(MeasurementAdapter):
        class Meta:
            name = "test-duplicate"

        @classmethod
        def claims_channel(cls, channel):
            return False

        def read(self, measurement, **kwargs):
            return None

    with pytest.raises(AlreadyRegisteredError, match="already registered"):
        register_adapter(Second)


def test_registering_the_same_class_twice_is_harmless(registered):
    """A module imported through two paths must not blow up at import time."""

    @registered
    class Reimported(MeasurementAdapter):
        class Meta:
            name = "test-reimported"

        @classmethod
        def claims_channel(cls, channel):
            return False

        def read(self, measurement, **kwargs):
            return None

    assert register_adapter(Reimported) is Reimported


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
        get_adapter("no-such-kind")

    assert "no-such-kind" in str(excinfo.value)
    assert "may not be installed" in str(excinfo.value)


def test_absence_can_be_checked_without_catching():
    assert has_adapter(TopographyMapAdapter.Meta.name)
    assert not has_adapter("no-such-kind")


def test_the_built_in_kinds_are_registered():
    kinds = get_kinds()

    assert set(kinds) >= {
        "topography-map",
        "uniform-line-scan",
        "nonuniform-line-scan",
    }
    assert set(get_adapters()) == set(kinds)


#
# Inferring the kind of a channel
#


@pytest.mark.parametrize(
    "channel,expected",
    [
        (FakeChannel(dim=2), TopographyMapAdapter),
        (FakeChannel(dim=1, is_uniform=True), UniformLineScanAdapter),
        (FakeChannel(dim=1, is_uniform=False), NonuniformLineScanAdapter),
    ],
)
def test_a_height_channel_is_claimed_by_exactly_one_built_in_type(channel, expected):
    assert infer_kind(channel) == expected.Meta.name
    # Exactly one: the others must not claim it, or the result would depend on
    # registration order.
    claiming = [
        adapter
        for adapter in get_adapters().values()
        if adapter.claims_channel(channel)
    ]
    assert len(claiming) == 1


def test_a_channel_that_is_not_height_data_is_claimed_by_nobody():
    """
    A tuple unit means the data is not a height (adhesion, current, ...).

    Such channels are listed in a file's inventory but no built-in adapter can import
    them, which is exactly the gap an external plugin fills.
    """
    channel = FakeChannel(dim=2, unit=("um", "nN"), name="adhesion")

    with pytest.raises(UnsupportedChannelError, match="adhesion"):
        infer_kind(channel)


def test_a_plugin_type_can_claim_a_channel_the_built_ins_reject(registered):
    """The registry must not need editing for a new modality to be importable."""
    channel = FakeChannel(dim=2, unit=("um", "nN"), name="adhesion")

    @registered
    class AdhesionMap(MeasurementAdapter):
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
