"""Tests for the in-flight dispatch guard in ``run_task``.

These cover the regression where ``refresh_cache`` re-dispatched the task it was
already running (because its terminal ``save()`` mutated significant fields),
causing concurrent ``refresh_cache`` executions on the same measurement.
"""

from unittest import mock

import pytest
from django.core.management import call_command

from topobank.manager.models import Topography
from topobank.taskapp.models import TaskStateModel
from topobank.taskapp.utils import run_task
from topobank.testing.factories import Topography1DFactory


def _set_state(topo, state, **extra):
    """Force task_state (and optional extra fields) directly in the DB."""
    Topography.objects.filter(pk=topo.pk).update(task_state=state, **extra)
    topo.refresh_from_db()


@pytest.mark.django_db
def test_run_task_skips_when_in_flight(django_capture_on_commit_callbacks):
    topo = Topography1DFactory()
    _set_state(topo, TaskStateModel.STARTED)

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        assert not run_task(topo)

    # Guard short-circuited: nothing dispatched, state untouched.
    assert callbacks == []
    assert topo.task_state == TaskStateModel.STARTED
    topo.refresh_from_db()
    assert topo.task_state == TaskStateModel.STARTED


@pytest.mark.django_db
def test_run_task_force_overrides_in_flight(django_capture_on_commit_callbacks):
    topo = Topography1DFactory()
    _set_state(topo, TaskStateModel.STARTED)
    old_task_id = topo.task_id

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        assert run_task(topo, force=True)

    # force=True bypasses the guard and re-pends the task under a new id.
    assert len(callbacks) == 1
    topo.refresh_from_db()
    assert topo.task_state == TaskStateModel.PENDING
    assert topo.task_id is not None and topo.task_id != old_task_id


@pytest.mark.django_db
def test_run_task_dispatches_when_notrun(django_capture_on_commit_callbacks):
    topo = Topography1DFactory()
    _set_state(topo, TaskStateModel.NOTRUN)

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        assert run_task(topo)

    # NOTRUN is not an in-flight state, so the first dispatch proceeds, and the
    # pending state is persisted without the caller saving.
    assert len(callbacks) == 1
    topo.refresh_from_db()
    assert topo.task_state == TaskStateModel.PENDING


@pytest.mark.django_db
def test_refresh_cache_does_not_redispatch_when_started(
    django_capture_on_commit_callbacks,
):
    """Regression: a task running refresh_cache must not dispatch itself again.

    The outer task sets task_state=STARTED before refresh_cache runs. The
    refresh writes what it computed without going through save(), so even
    though it changes significant fields, no second dispatch happens and the
    state stays STARTED.
    """
    topo = Topography1DFactory()
    # Simulate the running task and clear a significant field so refresh_cache
    # repopulates it; a save() of that change would dispatch.
    _set_state(topo, TaskStateModel.STARTED, data_source=None)

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        topo.refresh_cache()

    # No new celery dispatch was registered (the only callback deletes the
    # derived files the refresh replaced) and the state was not reset.
    with mock.patch(
        "topobank.taskapp.utils.task_dispatch.apply_async"
    ) as apply_async:
        for callback in callbacks:
            callback()
    apply_async.assert_not_called()
    topo.refresh_from_db()
    assert topo.task_state == TaskStateModel.STARTED
    # ...but the refresh still did its work (significant field repopulated).
    assert topo.data_source is not None


@pytest.mark.django_db
def test_factory_path_still_dispatches():
    """The NOTRUN factory path is unchanged: derived files are still produced."""
    topo = Topography1DFactory()
    # Topography1DFactory calls refresh_cache() in post_generation; the guard is
    # transparent there (state is NOTRUN), so derived files are present.
    assert topo.thumbnail is not None
    assert topo.squeezed_datafile is not None


@pytest.mark.django_db
def test_refresh_cache_command_background_persists_pending_state():
    """`refresh_cache --background` must leave the DB showing the pending state.

    Otherwise the operator would keep seeing the stale prior state (e.g.
    SUCCESS) until a worker starts. run_task() persists the pending state itself,
    so the DB reflects PENDING immediately.
    """
    topo = Topography1DFactory()
    _set_state(topo, TaskStateModel.SUCCESS)

    call_command("refresh_cache", "--background")

    topo.refresh_from_db()
    assert topo.task_state == TaskStateModel.PENDING
