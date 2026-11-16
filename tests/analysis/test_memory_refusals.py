"""
Results refused by the memory guard are tried again after a while (#1406).

A refusal is stored as an ordinary FAILURE, which counts as an existing
result, so nothing ever resubmitted it: refusals from a faulty estimate (#1393)
stood forever, and anonymous visitors cannot renew them. Refusals are now
marked in the result's metadata and resubmitted in place once they are older
than TOPOBANK_ANALYSIS_REFUSAL_RETRY_INTERVAL.
"""

import importlib
from datetime import timedelta

import pytest
from django.apps import apps
from django.utils import timezone

import topobank.testing.workflows  # noqa: F401
from topobank.analysis import sizing
from topobank.analysis.controller import AnalysisController
from topobank.analysis.exceptions import AnalysisTooLargeError
from topobank.analysis.models import Workflow, WorkflowResult
from topobank.analysis.tasks import (
    _fail_parent_on_dependency_failure,
    execute_workflow,
    perform_analysis,
    prepare_dependency_tasks,
)
from topobank.testing.factories import (
    SurfaceFactory,
    Topography1DFactory,
    TopographyAnalysisFactory,
)

GIB = 1024**3
WORKFLOW = "topobank.testing.test"


@pytest.fixture
def topography(user_alice):
    return Topography1DFactory(surface=SurfaceFactory(created_by=user_alice))


def _result(topography, task_state, metadata=None, task_error=None):
    extra = {} if task_error is None else {"task_error": task_error}
    return TopographyAnalysisFactory.create(
        subject_topography=topography,
        workflow_name=WORKFLOW,
        kwargs=Workflow(name=WORKFLOW).get_default_kwargs(),
        result=None,
        task_state=task_state,
        metadata=metadata or {},
        **extra,
    )


def _refusal(refused_at):
    return {sizing.MEMORY_REFUSAL_KEY: {"refused_at": refused_at.isoformat()}}


@pytest.mark.django_db
def test_refused_analysis_is_marked_in_its_metadata(topography, monkeypatch):
    def refuse(analysis):
        raise AnalysisTooLargeError(3 * 1024 * GIB, 64 * GIB)

    monkeypatch.setattr("topobank.analysis.tasks.check_memory_budget", refuse)
    analysis = _result(topography, WorkflowResult.PENDING)

    perform_analysis.apply(args=(analysis.id, True))

    analysis.refresh_from_db()
    # Still a failure carrying the message the user sees ...
    assert analysis.task_state == WorkflowResult.FAILURE
    assert analysis.task_error.startswith("This analysis is predicted to need")
    # ... but marked as a refusal
    refusal = analysis.metadata[sizing.MEMORY_REFUSAL_KEY]
    assert refusal["estimate"] == 3 * 1024 * GIB
    assert refusal["budget"] == 64 * GIB
    assert sizing.is_retryable_memory_refusal(analysis) is False  # just refused


@pytest.mark.django_db
def test_only_old_refusals_are_retryable(topography, settings):
    settings.TOPOBANK_ANALYSIS_REFUSAL_RETRY_INTERVAL = 3600
    now = timezone.now()

    fresh = _result(topography, WorkflowResult.FAILURE, _refusal(now - timedelta(minutes=5)))
    old = _result(topography, WorkflowResult.FAILURE, _refusal(now - timedelta(hours=2)))
    other_failure = _result(topography, WorkflowResult.FAILURE, task_error="Some bug")
    success = _result(topography, WorkflowResult.SUCCESS, _refusal(now - timedelta(days=9)))

    assert sizing.is_retryable_memory_refusal(fresh, now) is False
    assert sizing.is_retryable_memory_refusal(old, now) is True
    # Real failures are not retried automatically; Renew does that
    assert sizing.is_retryable_memory_refusal(other_failure, now) is False
    assert sizing.is_retryable_memory_refusal(success, now) is False


def _old_refusal():
    return _refusal(timezone.now() - timedelta(days=2))


@pytest.mark.django_db
def test_old_refusal_is_retried_in_place_by_a_viewer(
    topography, user_alice, user_bob, test_workflow
):
    """The retry keeps the result's row, parameters, permissions and owner: a
    viewer triggers it without taking it over, and results sharing its
    permission set (as dependencies do) are left alone."""
    kwargs = test_workflow.clean_kwargs({"a": 7})
    refused = _result(topography, WorkflowResult.FAILURE, _old_refusal())
    WorkflowResult.objects.filter(pk=refused.pk).update(kwargs=kwargs)
    sibling = TopographyAnalysisFactory.create(
        subject_topography=Topography1DFactory(surface=topography.surface),
        workflow_name=WORKFLOW,
        result=None,
        permissions=refused.permissions,
    )
    topography.surface.grant_permission(user_bob)
    refused.permissions.grant_for_user(user_bob, "view")
    users_before = sorted(
        (user.id, allow) for user, allow in refused.permissions.get_users()
    )

    controller = AnalysisController(user_bob, subjects=[topography], workflow=test_workflow)
    # Present, not missing: nothing new is created for it
    assert controller.subjects_without_analysis_results == []
    controller.trigger_missing_analyses()

    retried = WorkflowResult.objects.get(pk=refused.pk)
    assert retried.task_state == WorkflowResult.PENDING
    assert sizing.MEMORY_REFUSAL_KEY not in retried.metadata
    assert retried.kwargs == kwargs
    assert retried.permissions_id == refused.permissions_id
    assert retried.created_by == user_alice
    assert users_before == sorted(
        (user.id, allow) for user, allow in retried.permissions.get_users()
    )
    assert WorkflowResult.objects.filter(pk=sibling.pk).exists()
    assert (
        WorkflowResult.objects.filter(
            subject_topography=topography, workflow_name=WORKFLOW
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_recent_refusal_is_not_retried(topography, user_alice, test_workflow):
    refused = _result(topography, WorkflowResult.FAILURE, _refusal(timezone.now()))

    controller = AnalysisController(user_alice, subjects=[topography], workflow=test_workflow)
    assert controller.subjects_without_analysis_results == []
    controller.trigger_missing_analyses()

    refused.refresh_from_db()
    assert refused.task_state == WorkflowResult.FAILURE
    assert sizing.MEMORY_REFUSAL_KEY in refused.metadata


@pytest.mark.django_db
def test_concurrent_views_retry_a_refusal_once(topography, user_alice, test_workflow):
    """A view that read the old refusal before another view retried it (and
    the retry was refused again) must not retry it a second time."""
    refused = _result(topography, WorkflowResult.FAILURE, _old_refusal())
    first = AnalysisController(user_alice, subjects=[topography], workflow=test_workflow)
    second = AnalysisController(user_alice, subjects=[topography], workflow=test_workflow)
    assert len(first) == len(second) == 1  # both have read the old refusal

    first.trigger_missing_analyses()
    # The retry was quickly refused again
    fresh = _refusal(timezone.now())
    WorkflowResult.objects.filter(pk=refused.pk).update(
        task_state=WorkflowResult.FAILURE, metadata=fresh
    )
    second.trigger_missing_analyses()

    refused.refresh_from_db()
    assert refused.task_state == WorkflowResult.FAILURE
    assert refused.metadata == fresh


@pytest.mark.django_db
@pytest.mark.parametrize("rerun", ["result", "workflow"])
def test_a_new_attempt_clears_the_refusal_marker(topography, rerun):
    """Otherwise an unrelated failure of the new attempt would be retried as a
    refusal, with the old refusal time."""
    refused = _result(
        topography,
        WorkflowResult.FAILURE,
        {**_old_refusal(), "parent_workflow_result_id": 3},
    )

    if rerun == "result":
        refused.submit_again()
    else:
        Workflow(name=WORKFLOW).submit_again(refused)

    refused.refresh_from_db()
    assert refused.task_state == WorkflowResult.PENDING
    assert refused.metadata == {"parent_workflow_result_id": 3}


def _waiting_parent(topography, dependency):
    parent = _result(topography, WorkflowResult.PENDING_DEPENDENCIES)
    parent.dependencies = {"0": dependency.id}
    parent.save()
    return parent


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["chord callback", "dependency failure"])
def test_a_parent_inherits_the_refusal_of_its_dependency(topography, test_workflow, path):
    """So the parent is retried with the refused dependency instead of standing
    as an ordinary failure."""
    marker = _old_refusal()
    dependency = _result(
        topography,
        WorkflowResult.FAILURE,
        marker,
        task_error="This analysis is predicted to need about 3 TB",
    )
    parent = _waiting_parent(topography, dependency)

    if path == "chord callback":
        execute_workflow.apply(args=(parent.id,))
    else:
        _fail_parent_on_dependency_failure(parent.id, dependency, "request")

    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.FAILURE
    assert parent.task_error == dependency.task_error
    assert parent.metadata[sizing.MEMORY_REFUSAL_KEY] == marker[sizing.MEMORY_REFUSAL_KEY]
    assert sizing.is_retryable_memory_refusal(parent) is True


@pytest.mark.django_db
def test_an_old_refused_dependency_is_scheduled_again(topography, test_workflow):
    """Without forcing, a parent schedules a dependency refused a while ago
    again, but takes a recent refusal as final."""
    dep_workflow = Workflow(name=WORKFLOW)
    subject_hash = WorkflowResult.compute_subject_hash("topography", [topography.id])
    old, recent = (
        TopographyAnalysisFactory.create(
            subject_topography=topography,
            workflow_name=WORKFLOW,
            kwargs=dep_workflow.clean_kwargs(kwargs),
            subject_hash=subject_hash,
            result=None,
            task_state=WorkflowResult.FAILURE,
            metadata=metadata,
        )
        for kwargs, metadata in [
            (dict(a=1), _old_refusal()),
            (dict(b="A"), _refusal(timezone.now())),
        ]
    )
    parent = _result(topography, WorkflowResult.PENDING)
    WorkflowResult.objects.filter(pk=parent.pk).update(
        workflow_name="topobank.testing.test2",
        kwargs=Workflow(name="topobank.testing.test2").get_default_kwargs(),
    )
    parent.refresh_from_db()

    finished, scheduled = prepare_dependency_tasks(
        parent.function.get_dependencies(parent),
        force=False,
        user=parent.created_by,
        parent=parent,
    )

    assert [dep.id for dep in scheduled.values()] == [old.id]
    assert [dep.id for dep in finished.values()] == [recent.id]
    old.refresh_from_db()
    # Pended at once, so a concurrent parent waits for this attempt
    assert old.task_state == WorkflowResult.PENDING
    assert sizing.MEMORY_REFUSAL_KEY not in old.metadata


@pytest.mark.django_db
def test_migration_marks_existing_refusals(topography):
    message = (
        "This analysis is predicted to need about 3.0 TB of memory, more than the "
        "64.0 GB available to a single analysis, so it was not started."
    )
    refused = _result(topography, WorkflowResult.FAILURE, task_error=message)
    other = _result(topography, WorkflowResult.FAILURE, task_error="Some bug")
    migration = importlib.import_module(
        "topobank.analysis.migrations.0067_mark_memory_refusals"
    )

    migration.mark_memory_refusals(apps, None)

    refused.refresh_from_db()
    other.refresh_from_db()
    assert sizing.MEMORY_REFUSAL_KEY in refused.metadata
    assert sizing.MEMORY_REFUSAL_KEY not in other.metadata
    # Refused long enough ago, so it is retried on the next view
    refused.metadata[sizing.MEMORY_REFUSAL_KEY]["refused_at"] = (
        timezone.now() - timedelta(days=30)
    ).isoformat()
    assert sizing.is_retryable_memory_refusal(refused) is True
