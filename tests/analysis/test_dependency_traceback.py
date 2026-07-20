"""
Tests for issue #1345: when a workflow fails because a dependency failed, the
parent must surface the dependency's real error/traceback, not a generic one.
"""

import pytest

from topobank.analysis.models import Workflow, WorkflowResult
from topobank.analysis.tasks import execute_workflow, schedule_workflow
from topobank.testing.factories import TopographyAnalysisFactory

DEP_TRACEBACK = "DEP TRACEBACK: exploded at line 42"
DEP_ERROR = "boom in dep"


def _pending(topo, workflow_name="topobank.testing.test", **kwargs):
    from topobank.analysis.models import Workflow

    wf = Workflow(name=workflow_name)
    return TopographyAnalysisFactory.create(
        subject_topography=topo,
        workflow_name=workflow_name,
        kwargs=wf.get_default_kwargs(),
        result=None,
        task_state=WorkflowResult.PENDING,
        **kwargs,
    )


@pytest.mark.django_db
def test_parent_preserves_dependency_traceback_on_execute(two_topos, test_workflow):
    topo, _ = two_topos

    dep = _pending(topo)
    WorkflowResult.objects.filter(pk=dep.pk).update(
        task_state=WorkflowResult.FAILURE,
        task_error=DEP_ERROR,
        task_traceback=DEP_TRACEBACK,
    )

    parent = _pending(topo)
    parent.dependencies = {"0": dep.id}
    parent.save()

    # execute_workflow finds the failed dependency and must fail the parent
    # while carrying the dependency's real error/traceback.
    execute_workflow.apply(args=(parent.id,))

    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.FAILURE
    assert parent.task_error == DEP_ERROR
    assert parent.task_traceback == DEP_TRACEBACK


@pytest.mark.django_db
def test_schedule_workflow_copies_finished_failed_dependency_traceback(two_topos):
    """When dependencies already exist in a finished FAILURE state, the parent
    must inherit the failed dependency's error/traceback, not a generic message.
    """
    topo, _ = two_topos
    dep_wf = Workflow(name="topobank.testing.test")
    subject_hash = WorkflowResult.compute_subject_hash("topography", [topo.id])

    # Pre-create the two dependencies "topobank.testing.test2" declares, matching
    # the (workflow_name, subject_hash, kwargs) that prepare_dependency_tasks
    # looks up, already in a FAILED state.
    for dep_kwargs in [dict(a=1), dict(b="A")]:
        dep = TopographyAnalysisFactory.create(
            subject_topography=topo,
            workflow_name="topobank.testing.test",
            kwargs=dep_wf.clean_kwargs(dep_kwargs),
            subject_hash=subject_hash,
            result=None,
            task_state=WorkflowResult.FAILURE,
        )
        WorkflowResult.objects.filter(pk=dep.pk).update(
            task_error=DEP_ERROR, task_traceback=DEP_TRACEBACK
        )

    parent = _pending(topo, "topobank.testing.test2")

    schedule_workflow.apply(args=(parent.id, False))

    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.FAILURE
    assert parent.task_error == DEP_ERROR
    assert parent.task_traceback == DEP_TRACEBACK
