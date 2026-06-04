"""Tests for the in-flight dispatch guard in ``run_task``.

These cover the regression where ``refresh_cache`` re-dispatched the task it was
already running (because its terminal ``save()`` mutated significant fields),
causing concurrent ``refresh_cache`` executions on the same measurement.
"""

import pytest

from topobank.manager.models import Topography
from topobank.taskapp.models import TaskStateModel
from topobank.taskapp.utils import run_task
from topobank.testing.factories import Topography1DFactory


def _set_state(topo, state, **extra):
    """Force task_state (and optional extra fields) directly in the DB."""
    Topography.objects.filter(pk=topo.pk).update(task_state=state, **extra)
    topo.refresh_from_db()


@pytest.mark.django_db
def test_run_task_skips_when_in_flight(mocker):
    topo = Topography1DFactory()
    _set_state(topo, TaskStateModel.STARTED)

    spy = mocker.spy(topo, "set_pending_state")
    run_task(topo)

    # Guard short-circuited before set_pending_state; state untouched.
    assert spy.call_count == 0
    assert topo.task_state == TaskStateModel.STARTED


@pytest.mark.django_db
def test_run_task_force_overrides_in_flight(mocker):
    topo = Topography1DFactory()
    _set_state(topo, TaskStateModel.STARTED)

    spy = mocker.spy(topo, "set_pending_state")
    run_task(topo, force=True)

    # force=True bypasses the guard and re-pends the task.
    assert spy.call_count == 1
    assert topo.task_state == TaskStateModel.PENDING


@pytest.mark.django_db
def test_run_task_dispatches_when_notrun(mocker):
    topo = Topography1DFactory()
    _set_state(topo, TaskStateModel.NOTRUN)

    spy = mocker.spy(topo, "set_pending_state")
    run_task(topo)

    # NOTRUN is not an in-flight state, so the first dispatch proceeds.
    assert spy.call_count == 1
    assert topo.task_state == TaskStateModel.PENDING


@pytest.mark.django_db
def test_refresh_cache_does_not_redispatch_when_started(
    django_capture_on_commit_callbacks,
):
    """Regression: a task running refresh_cache must not dispatch itself again.

    The outer task sets task_state=STARTED before refresh_cache runs; the
    terminal save() in refresh_cache then re-enters run_task. With the guard,
    that re-entry is a no-op (no second celery dispatch, state stays STARTED).
    """
    topo = Topography1DFactory()
    # Simulate the running task and clear a significant field so refresh_cache
    # repopulates it -- pre-fix this is exactly what made the terminal save()
    # re-dispatch a second, concurrent task.
    _set_state(topo, TaskStateModel.STARTED, data_source=None)

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        topo.refresh_cache()

    # No new celery dispatch was registered and the state was not reset.
    assert callbacks == []
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
