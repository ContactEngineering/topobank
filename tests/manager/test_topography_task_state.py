"""
Tests for issue #1342: Topography.save() with a restricted update_fields must
still persist the pending task state that run_task sets in memory.

Otherwise a recompute is dispatched while the DB keeps task_state=SUCCESS
(get_task_state() then wrongly reports "done"), and the in-flight re-dispatch
guard — which keys off the persisted task_state — fails to prevent a second
concurrent edit from double-dispatching.
"""

import pytest

from topobank.manager.models import Topography
from topobank.testing.factories import Topography2DFactory


@pytest.mark.django_db
def test_save_update_fields_persists_pending_state():
    topo = Topography2DFactory()
    Topography.objects.filter(pk=topo.pk).update(task_state=Topography.SUCCESS)
    topo.refresh_from_db()
    assert topo.task_state == Topography.SUCCESS

    # A significant field changes, saved with a restricted update_fields.
    topo.size_x = topo.size_x + 1
    topo.save(update_fields=["size_x"])

    reloaded = Topography.objects.get(pk=topo.pk)
    assert reloaded.task_state == Topography.PENDING  # pending state persisted
    assert reloaded.size_x == topo.size_x  # the requested field still saved


@pytest.mark.django_db
def test_save_update_fields_no_change_keeps_state():
    """A save with update_fields that does not touch a significant field must
    not spuriously flip the state to pending."""
    topo = Topography2DFactory()
    Topography.objects.filter(pk=topo.pk).update(task_state=Topography.SUCCESS)
    topo.refresh_from_db()

    topo.name = "renamed"  # not a significant field
    topo.save(update_fields=["name"])

    assert Topography.objects.get(pk=topo.pk).task_state == Topography.SUCCESS


@pytest.mark.django_db
def test_persisted_pending_state_enables_inflight_guard():
    """Once the pending state is persisted, a concurrent handle sees it and is
    guarded from re-dispatching (run_task skips set_pending_state)."""
    topo = Topography2DFactory()
    Topography.objects.filter(pk=topo.pk).update(task_state=Topography.SUCCESS)
    topo.refresh_from_db()

    topo.size_x += 1
    topo.save(update_fields=["size_x"])
    assert Topography.objects.get(pk=topo.pk).task_state == Topography.PENDING
    submission_before = Topography.objects.get(pk=topo.pk).task_submission_time

    # A separate handle (concurrent worker) sees PENDING; its save must not
    # reset the submission time, i.e. no second dispatch is set up.
    concurrent = Topography.objects.get(pk=topo.pk)
    concurrent.size_x += 1
    concurrent.save(update_fields=["size_x"])

    assert (
        Topography.objects.get(pk=topo.pk).task_submission_time == submission_before
    )
