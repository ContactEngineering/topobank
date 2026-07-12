"""
Tests for topobank.analysis.tasks — the workflow scheduling/execution engine.

Celery eager mode is enabled in the test settings, so ``perform_analysis``
(which delegates to ``schedule_workflow`` and runs ``execute_workflow``
synchronously) executes the whole pipeline in-process, including dependency
resolution via chords.
"""

from contextlib import contextmanager

import pytest

# Registers the test workflow implementations ("topobank.testing.test",
# "...test2" with dependencies, etc.).
import topobank.testing.workflows  # noqa: F401
from topobank.analysis.models import Workflow, WorkflowResult
from topobank.analysis.tasks import (
    current_statistics,
    execute_workflow,
    perform_analysis,
    prepare_dependency_tasks,
    schedule_workflow,
)
from topobank.manager.models import Topography
from topobank.testing.factories import TopographyAnalysisFactory


def _pending_analysis(topo, workflow_name, **kwargs):
    wf = Workflow(name=workflow_name)
    return TopographyAnalysisFactory.create(
        subject_topography=topo,
        workflow_name=workflow_name,
        kwargs=wf.get_default_kwargs(),
        result=None,
        task_state=WorkflowResult.PENDING,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# current_statistics
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_current_statistics_empty():
    stats = current_statistics()
    assert stats == {
        "num_surfaces_excluding_publications": 0,
        "num_topographies_excluding_publications": 0,
        "num_analyses_excluding_publications": 0,
    }


@pytest.mark.django_db
def test_current_statistics_counts(two_topos):
    stats = current_statistics()
    assert stats["num_surfaces_excluding_publications"] >= 1
    assert stats["num_topographies_excluding_publications"] >= 2


@pytest.mark.django_db
def test_current_statistics_for_user(two_topos):
    user = Topography.objects.first().created_by
    stats = current_statistics(user=user)
    assert stats["num_surfaces_excluding_publications"] >= 1
    # A user with no data sees zeros.
    from topobank.testing.factories import UserFactory

    assert (
        current_statistics(user=UserFactory())[
            "num_surfaces_excluding_publications"
        ]
        == 0
    )


# ---------------------------------------------------------------------------
# Early-return guards (don't re-run completed analyses)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_schedule_workflow_skips_completed_without_force(two_topos, test_workflow):
    topo = Topography.objects.first()
    analysis = _pending_analysis(topo, "topobank.testing.test")
    WorkflowResult.objects.filter(pk=analysis.pk).update(
        task_state=WorkflowResult.SUCCESS
    )

    schedule_workflow.apply(args=(analysis.id, False))

    analysis.refresh_from_db()
    assert analysis.task_state == WorkflowResult.SUCCESS  # untouched, not re-run


@pytest.mark.django_db
def test_execute_workflow_skips_failed(two_topos, test_workflow):
    topo = Topography.objects.first()
    analysis = _pending_analysis(topo, "topobank.testing.test")
    WorkflowResult.objects.filter(pk=analysis.pk).update(
        task_state=WorkflowResult.FAILURE
    )

    execute_workflow.apply(args=(analysis.id,))

    analysis.refresh_from_db()
    assert analysis.task_state == WorkflowResult.FAILURE


# ---------------------------------------------------------------------------
# Dependency resolution
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_prepare_dependency_tasks_schedules_new_dependencies(two_topos, test_workflow):
    topo = Topography.objects.first()
    parent = _pending_analysis(topo, "topobank.testing.test2")

    dependencies = parent.function.get_dependencies(parent)
    finished, scheduled = prepare_dependency_tasks(
        dependencies, force=False, user=parent.created_by, parent=parent
    )

    # test2 declares two dependencies on "topobank.testing.test"; none exist yet.
    assert len(finished) == 0
    assert len(scheduled) == 2
    for dep in scheduled.values():
        assert dep.workflow_name == "topobank.testing.test"
        assert dep.metadata["parent_workflow_result_id"] == parent.id


@pytest.mark.django_db
def test_schedule_workflow_runs_dependencies_end_to_end(two_topos, test_workflow):
    topo = Topography.objects.first()
    analysis = _pending_analysis(topo, "topobank.testing.test2")

    # force=True so dependencies are (re)resolved and run.
    perform_analysis.apply(args=(analysis.id, True))

    analysis.refresh_from_db()
    assert analysis.task_state == WorkflowResult.SUCCESS

    # The two dependencies were created and ran successfully.
    deps = WorkflowResult.objects.filter(workflow_name="topobank.testing.test")
    assert deps.count() >= 2
    assert all(d.task_state == WorkflowResult.SUCCESS for d in deps)


# ---------------------------------------------------------------------------
# Parent attribution: the dispatching parent travels with the Celery task
# ---------------------------------------------------------------------------


@contextmanager
def _capture_execute_workflow_dispatches():
    """Record (args, kwargs) of every execute_workflow run via task_prerun —
    the same signal downstream SSE bridges read attribution from."""
    from celery.signals import task_prerun

    captured = []

    def _capture(sender=None, args=None, kwargs=None, **extra):
        if getattr(sender, "name", None) == execute_workflow.name:
            captured.append((tuple(args or ()), dict(kwargs or {})))

    task_prerun.connect(_capture, weak=False)
    try:
        yield captured
    finally:
        task_prerun.disconnect(_capture)


@pytest.mark.django_db
def test_dependency_dispatch_carries_parent_id(two_topos, test_workflow):
    topo = Topography.objects.first()
    analysis = _pending_analysis(topo, "topobank.testing.test2")

    with _capture_execute_workflow_dispatches() as captured:
        perform_analysis.apply(args=(analysis.id, True))

    dep_ids = set(
        WorkflowResult.objects.filter(
            workflow_name="topobank.testing.test"
        ).values_list("id", flat=True)
    )
    dep_runs = [(a, kw) for a, kw in captured if a[0] in dep_ids]
    parent_runs = [(a, kw) for a, kw in captured if a[0] == analysis.id]

    assert len(dep_runs) == 2
    for args_, kwargs_ in dep_runs:
        assert args_[1] is True  # executed as a dependency
        assert kwargs_["parent_id"] == analysis.id

    # The top-level run itself carries no parent, so it can never be
    # misclassified as someone's dependency.
    assert len(parent_runs) == 1
    assert parent_runs[0][1].get("parent_id") is None


@pytest.mark.django_db
def test_rerun_by_second_parent_attributes_to_that_parent(two_topos, test_workflow):
    """A second parent force-re-running shared dependency rows carries its own
    id in the task kwargs, while the rows keep the creation-time stamp of the
    parent that created them — per-execution attribution does not depend on
    (or mutate) the shared row."""
    topo = Topography.objects.first()
    parent_a = _pending_analysis(topo, "topobank.testing.test2")
    perform_analysis.apply(args=(parent_a.id, True))

    parent_b = _pending_analysis(topo, "topobank.testing.test2")
    with _capture_execute_workflow_dispatches() as captured:
        perform_analysis.apply(args=(parent_b.id, True))

    dep_rows = WorkflowResult.objects.filter(workflow_name="topobank.testing.test")
    dep_ids = set(dep_rows.values_list("id", flat=True))
    dep_runs = [(a, kw) for a, kw in captured if a[0] in dep_ids]

    assert len(dep_runs) == 2
    assert all(kw["parent_id"] == parent_b.id for _, kw in dep_runs)
    for dep in dep_rows:
        assert dep.metadata["parent_workflow_result_id"] == parent_a.id
