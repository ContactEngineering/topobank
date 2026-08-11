"""
Tests for the `kind` backfill in `manager.0086`.

The migration reconstructs the kind of every already-inspected measurement from
the typed columns, because reopening every stored data file would be far too slow.
The rules it uses are tested here directly against the same column combinations,
so that a change to either the rules or the columns they read has to be
deliberate.
"""

import importlib

import pytest

from topobank.manager.models import Measurement
from topobank.testing.factories import Topography1DFactory

# The module name starts with a digit, so it cannot be imported with `from ...
# import`.
backfill_module = importlib.import_module(
    "topobank.manager.migrations.0086_backfill_measurement_kind"
)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "resolution_x,resolution_y,is_periodic_editable,expected",
    [
        # Two-dimensional data: `resolution_y` is set only for maps.
        (128, 128, True, "topography-map"),
        # One-dimensional, periodicity still offered -> uniform.
        (128, None, True, "uniform-line-scan"),
        # One-dimensional, periodicity withdrawn -> non-uniform. Inspection clears
        # the flag only for non-uniform data, which is what makes it usable here.
        (128, None, False, "nonuniform-line-scan"),
        # Never inspected: no resolution was ever written, so nothing can be said.
        (None, None, True, None),
    ],
)
def test_the_backfill_reconstructs_the_kind_from_the_columns(
    resolution_x, resolution_y, is_periodic_editable, expected
):
    measurement = Topography1DFactory()
    Measurement.objects.filter(pk=measurement.pk).update(
        kind=None,
        resolution_x=resolution_x,
        resolution_y=resolution_y,
        is_periodic_editable=is_periodic_editable,
    )

    backfill_module.backfill_kind(_Apps(), None)

    assert Measurement.objects.get(pk=measurement.pk).kind == expected


@pytest.mark.django_db
def test_the_backfill_leaves_an_existing_kind_alone():
    """
    Only null kinds are filled in.

    A measurement created by a plugin carries a kind the column rules know nothing
    about; overwriting it with an inferred one would mislabel the data.
    """
    measurement = Topography1DFactory()
    Measurement.objects.filter(pk=measurement.pk).update(kind="plugin-kind")

    backfill_module.backfill_kind(_Apps(), None)

    assert Measurement.objects.get(pk=measurement.pk).kind == "plugin-kind"


@pytest.mark.django_db
def test_the_backfill_can_be_undone():
    measurement = Topography1DFactory()

    backfill_module.clear_kind(_Apps(), None)

    assert Measurement.objects.get(pk=measurement.pk).kind is None


class _Apps:
    """
    Stands in for the historical model registry a migration is handed.

    The backfill only reads columns that still exist on the current model, so
    handing it the real one exercises the same queries without having to drive the
    migration executor.
    """

    @staticmethod
    def get_model(app_label, model_name):
        assert (app_label, model_name) == ("manager", "Measurement")
        return Measurement
