"""
Identification of data channels by name.

These are pure unit tests of the resolution rules; the integration with actual
data files is covered in `tests/manager/test_measurement_channels.py`.
"""

import pytest

from topobank.measurements.channels import (
    AmbiguousChannelError,
    ChannelNotFoundError,
    occurrence_for,
    resolve_channel,
)


class TestOccurrenceFor:
    """The occurrence ordinal is recorded only when a name is ambiguous."""

    def test_unique_name_gets_no_ordinal(self):
        # A NULL ordinal is meaningful: it asserts the name was unambiguous.
        assert occurrence_for(["Height", "Phase"], 0) is None
        assert occurrence_for(["Height", "Phase"], 1) is None

    def test_single_channel_gets_no_ordinal(self):
        assert occurrence_for(["Height"], 0) is None

    def test_duplicate_name_gets_position_among_duplicates(self):
        names = ["Height", "Phase", "Height", "Height"]
        assert occurrence_for(names, 0) == 0
        assert occurrence_for(names, 2) == 1
        assert occurrence_for(names, 3) == 2
        # The unique name in between is still unambiguous.
        assert occurrence_for(names, 1) is None


class TestResolveChannel:
    def test_resolves_by_name_regardless_of_position(self):
        """The point of the whole exercise: order does not matter."""
        assert resolve_channel(["ZSensor", "Phase", "Height"], "Height") == 2
        # Same name, reordered file: still the same channel.
        assert resolve_channel(["Height", "Phase", "ZSensor"], "Height") == 0

    def test_missing_name_is_an_error(self):
        with pytest.raises(ChannelNotFoundError) as excinfo:
            resolve_channel(["ZSensor", "Phase"], "Height")
        message = str(excinfo.value)
        assert "Height" in message
        # The message lists what is available, so the user can pick again.
        assert "ZSensor" in message and "Phase" in message

    def test_no_silent_fallback_for_missing_name(self):
        """A vanished channel must never resolve to some other channel."""
        with pytest.raises(ChannelNotFoundError):
            resolve_channel(["Something else"], "Height")

    def test_duplicate_name_without_ordinal_is_ambiguous(self):
        """
        This is the case a non-null default ordinal would have hidden.

        A name recorded while it was unique, which now matches several channels,
        means the file or the reader changed. Resolving to the first match would
        silently change which data the measurement refers to, so it is an error.
        """
        with pytest.raises(AmbiguousChannelError) as excinfo:
            resolve_channel(["Height", "Height"], "Height")
        assert "unambiguous" in str(excinfo.value)

    def test_duplicate_name_with_ordinal_resolves(self):
        names = ["Height", "Phase", "Height"]
        assert resolve_channel(names, "Height", 0) == 0
        assert resolve_channel(names, "Height", 1) == 2

    def test_ordinal_out_of_range_is_an_error(self):
        with pytest.raises(ChannelNotFoundError):
            resolve_channel(["Height", "Height"], "Height", 2)

    def test_stale_ordinal_on_now_unique_name_is_tolerated(self):
        """
        A recorded ordinal is a disambiguator, not part of the identity.

        If the duplicate disappeared, the name alone identifies the channel again
        and the redundant ordinal is ignored (it is cleared on the next
        inspection). This is deliberately not an error: nothing is ambiguous.
        """
        assert resolve_channel(["Height"], "Height", 0) == 0
        assert resolve_channel(["Height"], "Height", 1) == 0
