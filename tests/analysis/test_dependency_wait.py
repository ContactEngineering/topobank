"""
A run whose chord fires while a shared dependency is pending or running again
(another parent's forced submit renewed it in place) waits for it instead of
failing with "Dependency 'x' failed." for a dependency that goes on to succeed.
"""

from unittest.mock import patch

import pytest

from topobank.analysis.models import Workflow, WorkflowResult
from topobank.analysis.tasks import (
    DEPENDENCY_WAIT_INTERVAL,
    DEPENDENCY_WAIT_LIMIT,
    execute_workflow,
)
from topobank.testing.factories import TopographyAnalysisFactory


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
def test_waits_for_an_unfinished_dependency(two_topos, test_workflow, state):
    topo, _ = two_topos
    dep = _analysis(topo, state)
    parent = _parent_of(topo, dep)

    # Called directly (not .apply()), so the request is not eager, as on a worker.
    with patch.object(execute_workflow, "apply_async") as requeue:
        requeue.return_value.id = "4f1c0d2e-0000-0000-0000-000000000001"
        execute_workflow(parent.id)

    requeue.assert_called_once()
    _, call = requeue.call_args
    assert call["countdown"] == DEPENDENCY_WAIT_INTERVAL
    assert call["kwargs"]["waited"] == DEPENDENCY_WAIT_INTERVAL
    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.PENDING_DEPENDENCIES
    assert str(parent.task_id) == "4f1c0d2e-0000-0000-0000-000000000001"
    assert not parent.task_error


@pytest.mark.django_db
def test_runs_once_the_dependency_has_succeeded(two_topos, test_workflow):
    topo, _ = two_topos
    dep = _analysis(topo, WorkflowResult.SUCCESS)
    parent = _parent_of(topo, dep)

    with patch.object(execute_workflow, "apply_async") as requeue:
        execute_workflow(parent.id, waited=DEPENDENCY_WAIT_INTERVAL)

    requeue.assert_not_called()
    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.SUCCESS


@pytest.mark.django_db
def test_gives_up_after_the_wait_limit_with_a_clear_message(two_topos, test_workflow):
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
def test_eager_execution_fails_at_once_instead_of_recursing(two_topos, test_workflow):
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
