"""
Tests for the channel inventory in `Measurement.file_info`.

A data file offers channels; the inventory records every one of them, in file
order, with what the inspection could tell about it -- including which kind, if
any, would import it. It supersedes the `channel_names` display cache, which is
kept in step for the REST API until the legacy columns go.
"""

import importlib
from types import SimpleNamespace

import pytest
from SurfaceTopography import open_topography

from topobank.manager.models import Measurement
from topobank.measurements.adapters import SurfaceTopographyAdapter
from topobank.measurements.schemas import ChannelInfo, TopographyMapFileInfo
from topobank.testing.data import FIXTURE_DATA_DIR
from topobank.testing.factories import Topography2DFactory

# Four channels: two height maps (`ZSensor`, `Height`) and two that are not
# heights at all (`AmplitudeError`, `Phase`), whose data has no unit.
MULTI_CHANNEL_FILE = "example3.di"

backfill_module = importlib.import_module(
    "topobank.manager.migrations.0092_backfill_channels"
)


def _channel(name, unit="nm", dim=2, is_uniform=True):
    """Just enough of a reader channel for the inventory to describe it."""
    return SimpleNamespace(name=name, unit=unit, dim=dim, is_uniform=is_uniform)


def _reader(*channels):
    return SimpleNamespace(channels=list(channels))


#
# Schema
#


def test_the_inventory_is_empty_until_inspected():
    assert TopographyMapFileInfo().channels == []


def test_a_channel_rejects_unknown_fields():
    """`extra="forbid"`: a typo must not become a silently stored key."""
    with pytest.raises(ValueError):
        ChannelInfo(name="Height", occurence=0)


#
# Describing channels
#


def test_every_channel_of_the_file_is_listed_with_its_kind():
    """
    Non-height channels are present, importable by no kind.

    That is the point of listing them: before, a channel nobody could import
    was indistinguishable from one that did not exist.
    """
    reader = open_topography(f"{FIXTURE_DATA_DIR}/{MULTI_CHANNEL_FILE}")

    channels = SurfaceTopographyAdapter.describe_channels(reader)

    assert [c.name for c in channels] == ["ZSensor", "AmplitudeError", "Phase", "Height"]
    assert [c.kind for c in channels] == [
        "topography-map",
        None,
        None,
        "topography-map",
    ]
    assert all(c.dim == 2 for c in channels)


def test_a_non_height_channel_keeps_its_lateral_unit_but_has_no_data_unit():
    reader = open_topography(f"{FIXTURE_DATA_DIR}/{MULTI_CHANNEL_FILE}")

    by_name = {c.name: c for c in SurfaceTopographyAdapter.describe_channels(reader)}

    assert by_name["Height"].unit == by_name["Height"].data_unit == "nm"
    assert by_name["Phase"].unit == "µm"
    assert by_name["Phase"].data_unit is None


def test_occurrence_is_recorded_only_when_a_name_is_duplicated():
    """
    A unique name records None, not 0.

    None asserts the name identified exactly one channel when recorded, so a
    reader that later exposes a second channel of that name is detected as an
    ambiguity rather than quietly resolving to the first match. Recording 0 for
    every unique name would give that guarantee away.
    """
    reader = _reader(_channel("Height"), _channel("Height"), _channel("Phase"))

    channels = SurfaceTopographyAdapter.describe_channels(reader)

    assert [(c.name, c.occurrence) for c in channels] == [
        ("Height", 0),
        ("Height", 1),
        ("Phase", None),
    ]


def test_a_channel_without_units_is_still_a_height_channel():
    """
    A missing unit is something the user supplies, not a disqualifier.

    Many text formats carry no unit at all; the channel is height data all the
    same, and `unit_editable` is how the inspection hands the gap to the user.
    Only a *tuple* unit -- a data unit different from the lateral one -- marks
    a channel as not being heights.
    """
    reader = _reader(_channel("Raw", unit=None))

    (channel,) = SurfaceTopographyAdapter.describe_channels(reader)

    assert channel.unit is None and channel.data_unit is None
    assert channel.kind == "topography-map"


#
# Inspection
#


@pytest.mark.django_db
def test_inspection_records_the_inventory():
    topo = Topography2DFactory(filename=MULTI_CHANNEL_FILE)

    channels = topo.info.channels

    assert [c.name for c in channels] == ["ZSensor", "AmplitudeError", "Phase", "Height"]
    assert channels[0].kind == "topography-map"
    assert channels[1].kind is None


@pytest.mark.django_db
def test_the_legacy_channel_names_are_kept_in_step():
    """
    `channel_names` is what the REST API reads until the legacy columns go.

    Its pairs are `(name, data unit)`, which for a non-height channel is None --
    the same value the old `_get_unit` helper produced.
    """
    topo = Measurement.objects.get(pk=Topography2DFactory(filename=MULTI_CHANNEL_FILE).pk)

    assert topo.channel_names == [
        [c.name, c.data_unit] for c in topo.info.channels
    ]
    assert topo.channel_names[1] == ["AmplitudeError", None]


@pytest.mark.django_db
def test_the_inventory_survives_a_round_trip_through_the_database():
    topo = Topography2DFactory(filename=MULTI_CHANNEL_FILE)

    reloaded = Measurement.objects.get(pk=topo.pk)

    assert reloaded.info.channels == topo.info.channels


#
# Backfill
#


class _Apps:
    """Stands in for the historical registry a migration is handed."""

    @staticmethod
    def get_model(app_label, model_name):
        assert (app_label, model_name) == ("manager", "Measurement")
        return Measurement


@pytest.mark.django_db
def test_the_backfill_supplies_what_the_pairs_know():
    """
    Name, data unit and occurrence; the rest waits for a re-inspection.

    The occurrence ordinal is derived purely from the names, so the backfill can
    compute it and a duplicated name is disambiguated from day one.
    """
    topo = Topography2DFactory()
    Measurement.objects.filter(pk=topo.pk).update(
        channel_names=[["Height", "nm"], ["Height", "nm"], ["Phase", None]],
        file_info={"kind": "topography-map", "resolution_x": 10, "resolution_y": 10},
    )

    backfill_module.backfill_channels(_Apps(), None)

    channels = Measurement.objects.get(pk=topo.pk).info.channels
    assert [(c.name, c.data_unit, c.occurrence) for c in channels] == [
        ("Height", "nm", 0),
        ("Height", "nm", 1),
        ("Phase", None, None),
    ]
    assert all(c.dim is None and c.unit is None and c.kind is None for c in channels)


@pytest.mark.django_db
def test_the_backfill_leaves_the_rest_of_the_document_alone():
    topo = Topography2DFactory()
    Measurement.objects.filter(pk=topo.pk).update(
        channel_names=[["Height", "nm"]],
        file_info={"kind": "topography-map", "resolution_x": 10, "resolution_y": 10},
    )

    backfill_module.backfill_channels(_Apps(), None)

    info = Measurement.objects.get(pk=topo.pk).info
    assert info.resolution_x == 10 and info.resolution_y == 10


@pytest.mark.django_db
def test_the_backfill_skips_never_inspected_measurements():
    topo = Topography2DFactory()
    Measurement.objects.filter(pk=topo.pk).update(channel_names=[], file_info={})

    backfill_module.backfill_channels(_Apps(), None)

    assert Measurement.objects.get(pk=topo.pk).file_info == {}


@pytest.mark.django_db
def test_the_backfill_can_be_undone():
    topo = Topography2DFactory()
    assert topo.info.channels  # populated by the inspection

    backfill_module.clear_channels(_Apps(), None)

    assert "channels" not in Measurement.objects.get(pk=topo.pk).file_info
    assert Measurement.objects.get(pk=topo.pk).info.channels == []
