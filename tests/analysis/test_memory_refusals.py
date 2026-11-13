"""
Results refused by the memory guard are tried again after a while (#1406).

A refusal is stored as an ordinary FAILURE, which counts as an existing
result, so nothing ever resubmitted it: refusals from a faulty estimate (#1393)
stood forever, and anonymous visitors cannot renew them. Refusals are now
marked in the result's metadata and count as missing once they are older than
TOPOBANK_ANALYSIS_REFUSAL_RETRY_INTERVAL.
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
from topobank.analysis.tasks import perform_analysis
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


@pytest.mark.django_db
def test_old_refusal_counts_as_missing_and_is_resubmitted(
    topography, user_alice, test_workflow
):
    refused = _result(
        topography, WorkflowResult.FAILURE, _refusal(timezone.now() - timedelta(days=2))
    )

    controller = AnalysisController(user_alice, subjects=[topography], workflow=test_workflow)
    assert controller.subjects_without_analysis_results == [topography]

    controller.trigger_missing_analyses()

    # The refused result was replaced by a new one
    assert not WorkflowResult.objects.filter(pk=refused.pk).exists()
    assert WorkflowResult.objects.filter(
        subject_topography=topography, workflow_name=WORKFLOW
    ).exclude(task_state=WorkflowResult.FAILURE).exists()


@pytest.mark.django_db
def test_recent_refusal_is_not_resubmitted(topography, user_alice, test_workflow):
    _result(topography, WorkflowResult.FAILURE, _refusal(timezone.now()))

    controller = AnalysisController(user_alice, subjects=[topography], workflow=test_workflow)

    assert controller.subjects_without_analysis_results == []


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
