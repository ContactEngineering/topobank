"""
Tests for issue #1342: Measurement.save() with a restricted update_fields must
still persist the pending task state that run_task sets in memory.

Otherwise a recompute is dispatched while the DB keeps task_state=SUCCESS
(get_task_state() then wrongly reports "done"), and the in-flight re-dispatch
guard — which keys off the persisted task_state — fails to prevent a second
concurrent edit from double-dispatching.
"""

import pytest

from topobank.manager.models import Measurement
from topobank.testing.factories import Topography2DFactory


@pytest.mark.django_db
def test_save_update_fields_persists_pending_state():
    topo = Topography2DFactory()
    Measurement.objects.filter(pk=topo.pk).update(task_state=Measurement.SUCCESS)
    topo.refresh_from_db()
    assert topo.task_state == Measurement.SUCCESS

    # Significant metadata changes, saved with a restricted update_fields.
    topo.update_metadata(size_x=topo.meta.size_x + 1)

    reloaded = Measurement.objects.get(pk=topo.pk)
    assert reloaded.task_state == Measurement.PENDING  # pending state persisted
    # the requested field still saved
    assert reloaded.meta.size_x == topo.meta.size_x


@pytest.mark.django_db
@pytest.mark.parametrize("update_fields", [None, ["data_source"]])
def test_selecting_another_channel_triggers_a_refresh(update_fields):
    """
    `data_source` is significant, but no schema can declare it.

    It selects *which* channel the metadata describes rather than describing it,
    so it is not a field of the metadata document -- and the document comparison
    in `save()` therefore cannot see it changing. It needs its own comparison:
    selecting another channel invalidates everything derived from the data.
    """
    topo = Topography2DFactory()
    Measurement.objects.filter(pk=topo.pk).update(task_state=Measurement.SUCCESS)
    topo.refresh_from_db()

    topo.data_source = topo.data_source + 1
    topo.save(update_fields=update_fields)

    assert Measurement.objects.get(pk=topo.pk).task_state == Measurement.PENDING


@pytest.mark.django_db
def test_saving_an_unchanged_channel_selection_does_not_refresh():
    """The comparison must not fire on every save that includes the field."""
    topo = Topography2DFactory()
    Measurement.objects.filter(pk=topo.pk).update(task_state=Measurement.SUCCESS)
    topo.refresh_from_db()

    topo.save(update_fields=["data_source"])

    assert Measurement.objects.get(pk=topo.pk).task_state == Measurement.SUCCESS


@pytest.mark.django_db
def test_save_update_fields_no_change_keeps_state():
    """A save with update_fields that does not touch a significant field must
    not spuriously flip the state to pending."""
    topo = Topography2DFactory()
    Measurement.objects.filter(pk=topo.pk).update(task_state=Measurement.SUCCESS)
    topo.refresh_from_db()

    topo.name = "renamed"  # not a significant field
    topo.save(update_fields=["name"])

    assert Measurement.objects.get(pk=topo.pk).task_state == Measurement.SUCCESS


@pytest.mark.django_db
def test_persisted_pending_state_enables_inflight_guard():
    """Once the pending state is persisted, a concurrent handle sees it and is
    guarded from re-dispatching (run_task skips set_pending_state)."""
    topo = Topography2DFactory()
    Measurement.objects.filter(pk=topo.pk).update(task_state=Measurement.SUCCESS)
    topo.refresh_from_db()

    topo.update_metadata(size_x=topo.meta.size_x + 1)
    assert Measurement.objects.get(pk=topo.pk).task_state == Measurement.PENDING
    submission_before = Measurement.objects.get(pk=topo.pk).task_submission_time

    # A separate handle (concurrent worker) sees PENDING; its save must not
    # reset the submission time, i.e. no second dispatch is set up.
    concurrent = Measurement.objects.get(pk=topo.pk)
    concurrent.update_metadata(size_x=concurrent.meta.size_x + 1)

    assert (
        Measurement.objects.get(pk=topo.pk).task_submission_time == submission_before
    )
