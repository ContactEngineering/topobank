"""
Tests for the measurement-handler registry.

The registry is the seam that lets a package outside TopoBank add a kind of
measurement, so what matters here is the contract it offers such a package:
registration is keyed by a stable name, lookup fails loudly for an unknown kind,
and which handler claims a data channel is decided by the handlers themselves.
"""

import pytest

from topobank.measurements.registry import (
    AlreadyRegisteredError,
    MeasurementRegistryError,
    UnknownMeasurementKindError,
    UnsupportedChannelError,
    get_kinds,
    get_handler,
    get_handlers,
    has_handler,
    infer_kind,
    register_handler,
    unregister_handler,
)
from topobank.measurements.handlers import (
    MeasurementHandler,
    NonuniformLineScanHandler,
    TopographyMapHandler,
    UniformLineScanHandler,
)


class FakeChannel:
    """The handful of channel attributes the built-in handlers look at."""

    def __init__(self, dim=2, unit="um", is_uniform=True, name="channel"):
        self.dim = dim
        self.unit = unit
        self.is_uniform = is_uniform
        self.name = name


@pytest.fixture
def registered():
    """Register a throwaway handler and remove it again afterwards."""
    registered_kinds = []

    def register(cls):
        register_handler(cls)
        registered_kinds.append(cls.Meta.kind)
        return cls

    yield register

    for kind in registered_kinds:
        unregister_handler(kind)


#
# Registration
#


def test_a_registered_type_is_returned_as_a_singleton(registered):
    @registered
    class Spectrum(MeasurementHandler):
        class Meta:
            kind = "test-singleton"
            display_name = "Test singleton"

        @classmethod
        def claims_channel(cls, channel):
            return False

        def read(self, measurement, **kwargs):
            return None

    # The decorator returns the class, so it stays usable under its own name...
    assert Spectrum.Meta.kind == "test-singleton"
    # ...while the registry holds one instance of it, handed out every time.
    assert get_handler("test-singleton") is get_handler(
        "test-singleton"
    )
    assert isinstance(get_handler("test-singleton"), Spectrum)


def test_a_type_without_a_name_is_refused():
    class Nameless(MeasurementHandler):
        class Meta:
            kind = None

        @classmethod
        def claims_channel(cls, channel):
            return False

        def read(self, measurement, **kwargs):
            return None

    with pytest.raises(MeasurementRegistryError, match="does not declare"):
        register_handler(Nameless)


def test_two_types_cannot_claim_the_same_kind(registered):
    @registered
    class First(MeasurementHandler):
        class Meta:
            kind = "test-duplicate"

        @classmethod
        def claims_channel(cls, channel):
            return False

        def read(self, measurement, **kwargs):
            return None

    class Second(MeasurementHandler):
        class Meta:
            kind = "test-duplicate"

        @classmethod
        def claims_channel(cls, channel):
            return False

        def read(self, measurement, **kwargs):
            return None

    with pytest.raises(AlreadyRegisteredError, match="already registered"):
        register_handler(Second)


def test_registering_the_same_class_twice_is_harmless(registered):
    """A module imported through two paths must not blow up at import time."""

    @registered
    class Reimported(MeasurementHandler):
        class Meta:
            kind = "test-reimported"

        @classmethod
        def claims_channel(cls, channel):
            return False

        def read(self, measurement, **kwargs):
            return None

    assert register_handler(Reimported) is Reimported


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
        get_handler("no-such-kind")

    assert "no-such-kind" in str(excinfo.value)
    assert "may not be installed" in str(excinfo.value)


def test_absence_can_be_checked_without_catching():
    assert has_handler(TopographyMapHandler.Meta.kind)
    assert not has_handler("no-such-kind")


def test_the_built_in_kinds_are_registered():
    kinds = get_kinds()

    assert set(kinds) >= {
        "topography-map",
        "uniform-line-scan",
        "nonuniform-line-scan",
    }
    assert set(get_handlers()) == set(kinds)


#
# Inferring the kind of a channel
#


@pytest.mark.parametrize(
    "channel,expected",
    [
        (FakeChannel(dim=2), TopographyMapHandler),
        (FakeChannel(dim=1, is_uniform=True), UniformLineScanHandler),
        (FakeChannel(dim=1, is_uniform=False), NonuniformLineScanHandler),
    ],
)
def test_a_height_channel_is_claimed_by_exactly_one_built_in_type(channel, expected):
    assert infer_kind(channel) == expected.Meta.kind
    # Exactly one: the others must not claim it, or the result would depend on
    # registration order.
    claiming = [
        handler
        for handler in get_handlers().values()
        if handler.claims_channel(channel)
    ]
    assert len(claiming) == 1


def test_a_channel_that_is_not_height_data_is_claimed_by_nobody():
    """
    A tuple unit means the data is not a height (adhesion, current, ...).

    Such channels are listed in a file's inventory but no built-in handler can import
    them, which is exactly the gap an external plugin fills.
    """
    channel = FakeChannel(dim=2, unit=("um", "nN"), name="adhesion")

    with pytest.raises(UnsupportedChannelError, match="adhesion"):
        infer_kind(channel)


def test_a_plugin_type_can_claim_a_channel_the_built_ins_reject(registered):
    """The registry must not need editing for a new modality to be importable."""
    channel = FakeChannel(dim=2, unit=("um", "nN"), name="adhesion")

    @registered
    class AdhesionMap(MeasurementHandler):
        class Meta:
            kind = "test-adhesion-map"

        @classmethod
        def claims_channel(cls, other):
            return isinstance(other.unit, tuple) and other.unit[1] == "nN"

        def read(self, measurement, **kwargs):
            return None

    assert infer_kind(channel) == "test-adhesion-map"


def test_a_dimension_no_type_handles_is_rejected():
    with pytest.raises(UnsupportedChannelError):
        infer_kind(FakeChannel(dim=3))
