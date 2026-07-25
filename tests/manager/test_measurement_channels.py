"""
Channel selection and kind determination against real data files.

``example3.di`` is the interesting fixture here: it has four channels, two of which
hold height data (``ZSensor`` at index 0 and ``Height`` at index 3) and two of which
do not (``AmplitudeError``, ``Phase``). That covers name-based selection where the
position differs, and channels that no measurement type claims.
"""

import pytest

from topobank.manager.models import Measurement
from topobank.measurements.channels import (
    AmbiguousChannelError,
    ChannelNotFoundError,
    UnsupportedChannelError,
)
from topobank.testing.factories import ManifestFactory, SurfaceFactory

MULTI_CHANNEL_DATAFILE = "example3.di"


def make_measurement(surface, filename=MULTI_CHANNEL_DATAFILE, name=None, **kwargs):
    """Create an uninspected measurement backed by a fixture file."""
    datafile = ManifestFactory(filename=filename, permissions=surface.permissions)
    measurement = Measurement(
        surface=surface,
        created_by=surface.created_by,
        permissions=surface.permissions,
        name=name or filename,
        datafile=datafile,
        **kwargs,
    )
    measurement.save()
    return measurement


@pytest.fixture
def surface():
    return SurfaceFactory()


@pytest.mark.django_db
class TestFirstInspection:
    def test_default_channel_is_selected_and_recorded_by_name(self, surface):
        measurement = make_measurement(surface)
        assert measurement.channel_name is None  # not inspected yet

        measurement.refresh_cache()

        assert measurement.channel_name == "ZSensor"
        # The name is unique in this file, so no tie-breaker is stored.
        assert measurement.channel_occurrence is None
        assert measurement.kind == "topography-map"

    def test_channel_inventory_is_recorded(self, surface):
        measurement = make_measurement(surface)
        measurement.refresh_cache()

        channels = measurement.info.channels
        assert [channel.name for channel in channels] == [
            "ZSensor",
            "AmplitudeError",
            "Phase",
            "Height",
        ]
        # Every entry says which kind it would be imported as; the two channels
        # that do not hold height data are not claimed by any registered type.
        by_name = {channel.name: channel for channel in channels}
        assert by_name["ZSensor"].kind == "topography-map"
        assert by_name["Height"].kind == "topography-map"
        assert by_name["AmplitudeError"].kind is None
        assert by_name["Phase"].kind is None
        assert not by_name["Phase"].is_supported
        # A non-height channel is still described, including its data unit, so the
        # UI can list it and a future measurement type can claim it.
        assert by_name["Phase"].dim == 2
        assert by_name["ZSensor"].data_unit == "nm"


@pytest.mark.django_db
class TestNamedSelection:
    def test_channel_can_be_selected_by_name(self, surface):
        """Selecting `Height` reaches index 3, not the default index 0."""
        measurement = make_measurement(surface, channel_name="Height")
        measurement.refresh_cache()

        assert measurement.channel_name == "Height"
        assert measurement.kind == "topography-map"
        assert measurement.is_metadata_complete
        # The data really was read from that channel.
        assert measurement.read() is not None

    def test_position_does_not_matter(self, surface):
        """
        Two measurements on the same file, different channels.

        Nothing about either record refers to a position in the file, which is the
        entire point: a reader that reorders its channels cannot silently swap the
        data under an existing measurement.
        """
        first = make_measurement(surface, channel_name="ZSensor")
        first.refresh_cache()
        # (surface, name) is unique, so the second record needs its own name.
        second = make_measurement(surface, channel_name="Height", name="second")
        second.refresh_cache()

        assert first.channel_name == "ZSensor"
        assert second.channel_name == "Height"
        assert first.read().physical_sizes == second.read().physical_sizes

    def test_unknown_channel_name_is_an_error(self, surface):
        measurement = make_measurement(surface, channel_name="NoSuchChannel")
        with pytest.raises(ChannelNotFoundError) as excinfo:
            measurement.refresh_cache()
        # Deliberately not a silent fallback to the default channel.
        assert "NoSuchChannel" in str(excinfo.value)
        assert "ZSensor" in str(excinfo.value)

    def test_non_height_channel_is_rejected_with_a_clear_error(self, surface):
        """
        Channels that no type claims cannot be imported - yet.

        They are listed in the inventory, so registering a measurement type for
        them is all it takes to make them importable.
        """
        measurement = make_measurement(surface, channel_name="Phase")
        with pytest.raises(UnsupportedChannelError) as excinfo:
            measurement.refresh_cache()
        assert "Phase" in str(excinfo.value)
        assert "No measurement type is registered" in str(excinfo.value)

    def test_ambiguous_name_is_reported(self, surface, mocker):
        """
        A name that has become ambiguous is an error, not a guess.

        No fixture file has duplicate channel names, so the reader's report is
        patched to simulate one appearing after the fact.
        """
        measurement = make_measurement(surface, channel_name="ZSensor")
        measurement.refresh_cache()
        assert measurement.channel_occurrence is None

        from topobank.measurements.types import SurfaceTopographyType

        original = SurfaceTopographyType.sniff.__func__

        def duplicate_channel_sniff(cls, m):
            inspection = original(cls, m)
            inspection.channels[3].name = "ZSensor"  # 'Height' becomes a duplicate
            return inspection

        mocker.patch.object(
            SurfaceTopographyType,
            "sniff",
            classmethod(duplicate_channel_sniff),
        )
        with pytest.raises(AmbiguousChannelError) as excinfo:
            measurement.refresh_cache()
        assert "ZSensor" in str(excinfo.value)


@pytest.mark.django_db
class TestChangingChannel:
    def test_switching_channel_reinspects(self, surface):
        measurement = make_measurement(surface)
        measurement.refresh_cache()
        assert measurement.channel_name == "ZSensor"

        measurement.channel_name = "Height"
        measurement.save(update_fields=["channel_name"])
        measurement.refresh_cache()

        assert measurement.channel_name == "Height"
        assert measurement.kind == "topography-map"

    def test_switching_channel_is_a_significant_change(self, surface):
        """It changes which data the measurement refers to, so it must re-run."""
        measurement = make_measurement(surface)
        measurement.refresh_cache()
        Measurement.objects.filter(pk=measurement.pk).update(
            task_state=Measurement.SUCCESS
        )
        measurement.refresh_from_db()

        measurement.channel_name = "Height"
        measurement.save(update_fields=["channel_name"])

        assert (
            Measurement.objects.get(pk=measurement.pk).task_state
            == Measurement.PENDING
        )

    def test_kind_changes_with_dimensionality_and_metadata_carries_over(self, surface):
        """
        A channel of different dimensionality changes the kind of the measurement.

        The metadata that both kinds have in common survives; what does not apply
        to the new kind is dropped rather than causing a validation failure.
        """
        measurement = make_measurement(surface, filename="example4.txt")
        measurement.refresh_cache()
        assert measurement.kind == "topography-map"
        measurement.update_metadata(detrend_mode="height")

        # Re-inspect as a line scan by pointing the record at a 1D file. This
        # stands in for selecting a 1D channel of a multi-channel file.
        measurement.datafile = ManifestFactory(
            filename="line_scan_1.asc", permissions=surface.permissions
        )
        measurement.channel_name = None
        measurement.save()
        measurement.refresh_cache()

        assert measurement.kind == "nonuniform-line-scan"
        # Shared metadata survived the change of kind...
        assert measurement.meta.detrend_mode == "height"
        # ...and the fields that do not apply to the new kind are simply gone.
        assert "size_y" not in measurement.metadata
        assert "is_periodic" not in measurement.metadata


@pytest.mark.django_db
class TestLegacyChannelIndex:
    """
    Containers written before channels were named record an index.

    The index is carried as a hint and consumed by the first inspection, which
    stores the resolved name. Falling back to the reader's default channel instead
    would silently pick different data for any file whose default is not the
    recorded index - exactly the case this fixture has.
    """

    def test_index_hint_resolves_to_a_name(self, surface):
        # Index 3 is 'Height'; the reader's default is index 0 ('ZSensor').
        measurement = make_measurement(surface, channel_index_hint=3)
        measurement.refresh_cache()

        assert measurement.channel_name == "Height"
        # Consumed: the name is authoritative from now on.
        assert measurement.channel_index_hint is None

    def test_out_of_range_hint_falls_back_to_the_default_channel(self, surface):
        """
        A hint that the file cannot satisfy is not worth failing over.

        Unlike a recorded *name*, an out-of-range index carries no trustworthy
        identity to preserve, so the default channel is used and the resolved name
        stored.
        """
        measurement = make_measurement(surface, channel_index_hint=99)
        measurement.refresh_cache()

        assert measurement.channel_name == "ZSensor"
        assert measurement.channel_index_hint is None
