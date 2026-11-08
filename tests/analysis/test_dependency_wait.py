"""
A run whose chord fires while a shared dependency is pending or running again
(another parent's forced submit renewed it in place) waits for it instead of
failing with "Dependency 'x' failed." for a dependency that goes on to succeed.
"""

from unittest.mock import patch

import pytest

from topobank.analysis import tasks
from topobank.analysis.models import Workflow, WorkflowResult
from topobank.analysis.tasks import (
    DEPENDENCY_WAIT_INTERVAL,
    DEPENDENCY_WAIT_LIMIT,
    execute_workflow,
)
from topobank.taskapp.celeryapp import app
from topobank.testing.factories import TopographyAnalysisFactory


@pytest.fixture
def worker_mode():
    """As on a worker: task_always_eager off, so countdowns are honoured. The
    tests patch apply_async, so nothing is published."""
    # The Django settings carry the namespaced key, which takes precedence.
    keys = ("CELERY_TASK_ALWAYS_EAGER", "task_always_eager")
    saved = {key: app.conf.get(key) for key in keys}
    app.conf.update({key: False for key in keys})
    try:
        assert not app.conf.task_always_eager
        yield
    finally:
        app.conf.update(saved)


def _analysis(topo, task_state=WorkflowResult.PENDING):
    wf = Workflow(name="topobank.testing.test")
    return TopographyAnalysisFactory.create(
        subject_topography=topo,
        workflow_name="topobank.testing.test",
        kwargs=wf.get_default_kwargs(),
        result=None,
        task_state=task_state,
    )


def _parent_of(topo, dep):
    parent = _analysis(topo, WorkflowResult.PENDING_DEPENDENCIES)
    parent.dependencies = {"features:0": dep.id}
    parent.save()
    return parent


@pytest.mark.django_db
@pytest.mark.parametrize("state", [WorkflowResult.PENDING, WorkflowResult.STARTED])
@pytest.mark.parametrize("via_apply", [False, True])
def test_waits_for_an_unfinished_dependency(
    two_topos, test_workflow, worker_mode, state, via_apply
):
    topo, _ = two_topos
    dep = _analysis(topo, state)
    parent = _parent_of(topo, dep)

    with patch.object(execute_workflow, "apply_async") as requeue:
        if via_apply:
            # schedule_workflow's shortcut: .apply() on a worker, so the request
            # is eager but the countdown of the re-queued task is honoured.
            execute_workflow.apply(args=(parent.id,), kwargs={"queue": "analysis"})
        else:
            execute_workflow(parent.id)

    requeue.assert_called_once()
    _, call = requeue.call_args
    assert call["countdown"] == DEPENDENCY_WAIT_INTERVAL
    assert call["kwargs"]["waited"] == DEPENDENCY_WAIT_INTERVAL
    if via_apply:
        assert call["queue"] == call["kwargs"]["queue"] == "analysis"
    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.PENDING_DEPENDENCIES
    assert str(parent.task_id) == str(call["task_id"])
    assert not parent.task_error


def _changing_parent_meanwhile(parent_id, **fields):
    """_read_dependencies, but the parent row changes right after the read, as
    when a dependency's worker fails it or a resubmission takes it over."""
    read = tasks._read_dependencies

    def read_then_change(analysis):
        deps = read(analysis)
        WorkflowResult.objects.filter(pk=parent_id).update(**fields)
        return deps

    return patch.object(tasks, "_read_dependencies", read_then_change)


@pytest.mark.django_db
def test_a_waiting_run_does_not_reopen_a_parent_failed_meanwhile(
    two_topos, test_workflow, worker_mode
):
    topo, _ = two_topos
    dep = _analysis(topo, WorkflowResult.PENDING)
    parent = _parent_of(topo, dep)

    with (
        _changing_parent_meanwhile(
            parent.id, task_state=WorkflowResult.FAILURE, task_error="dep failed"
        ),
        patch.object(execute_workflow, "apply_async") as requeue,
    ):
        execute_workflow(parent.id)

    requeue.assert_not_called()
    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.FAILURE
    assert parent.task_error == "dep failed"


@pytest.mark.django_db
def test_a_stale_run_leaves_a_resubmission_alone(
    two_topos, test_workflow, worker_mode
):
    topo, _ = two_topos
    dep = _analysis(topo, WorkflowResult.PENDING)
    parent = _parent_of(topo, dep)
    resubmission = "4f1c0d2e-0000-0000-0000-000000000002"

    with (
        _changing_parent_meanwhile(parent.id, task_id=resubmission),
        patch.object(execute_workflow, "apply_async") as requeue,
    ):
        execute_workflow(parent.id)

    requeue.assert_not_called()
    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.PENDING_DEPENDENCIES
    assert str(parent.task_id) == resubmission


@pytest.mark.django_db
def test_runs_once_the_dependency_has_succeeded(two_topos, test_workflow, worker_mode):
    topo, _ = two_topos
    dep = _analysis(topo, WorkflowResult.SUCCESS)
    parent = _parent_of(topo, dep)

    with patch.object(execute_workflow, "apply_async") as requeue:
        execute_workflow(parent.id, waited=DEPENDENCY_WAIT_INTERVAL)

    requeue.assert_not_called()
    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.SUCCESS


@pytest.mark.django_db
def test_gives_up_after_the_wait_limit_with_a_clear_message(
    two_topos, test_workflow, worker_mode
):
    topo, _ = two_topos
    dep = _analysis(topo, WorkflowResult.PENDING)
    parent = _parent_of(topo, dep)

    with (
        patch.object(execute_workflow, "apply_async") as requeue,
        pytest.raises(RuntimeError),
    ):
        execute_workflow(parent.id, waited=DEPENDENCY_WAIT_LIMIT)

    requeue.assert_not_called()
    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.FAILURE
    assert parent.task_error == (
        f"Dependency 'features:0' (topobank.testing.test #{dep.id}) was still "
        "pending when this workflow was due to start, probably because another "
        "run submitted it again. Submit this workflow again."
    )


@pytest.mark.django_db
def test_always_eager_fails_at_once_instead_of_recursing(two_topos, test_workflow):
    topo, _ = two_topos
    dep = _analysis(topo, WorkflowResult.STARTED)
    parent = _parent_of(topo, dep)

    execute_workflow.apply(args=(parent.id,))

    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.FAILURE
    assert "was still running when this workflow was due to start" in parent.task_error


@pytest.mark.django_db
def test_a_failed_dependency_without_an_error_is_named(two_topos, test_workflow):
    topo, _ = two_topos
    dep = _analysis(topo, WorkflowResult.FAILURE)
    parent = _parent_of(topo, dep)

    execute_workflow.apply(args=(parent.id,))

    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.FAILURE
    assert parent.task_error == (
        f"Dependency 'features:0' (topobank.testing.test #{dep.id}) failed "
        "without an error message."
    )


@pytest.mark.django_db
def test_a_failed_dependency_is_reported_even_if_another_is_unfinished(
    two_topos, test_workflow, worker_mode
):
    topo, _ = two_topos
    pending = _analysis(topo, WorkflowResult.PENDING)
    failed = _analysis(topo, WorkflowResult.FAILURE)
    failed.task_error = "Out of memory"
    failed.task_traceback = "Traceback: ..."
    failed.save()
    parent = _analysis(topo, WorkflowResult.PENDING_DEPENDENCIES)
    # The unfinished one first, so it would be found first.
    parent.dependencies = {"features:0": pending.id, "features:1": failed.id}
    parent.save()

    with (
        patch.object(execute_workflow, "apply_async") as requeue,
        pytest.raises(RuntimeError),
    ):
        execute_workflow(parent.id)

    requeue.assert_not_called()
    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.FAILURE
    assert parent.task_error == "Out of memory"
    assert parent.task_traceback == "Traceback: ..."
