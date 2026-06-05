"""
Functional tests for the task-state machine in ``topobank.taskapp.models``.

``TaskStateModel`` reconciles a *self-reported* task state (written to the DB by
the task runner) with what Celery reports. These tests drive every branch of
that reconciliation, plus the progress / error / duration helpers, by putting a
``WorkflowResult`` into a specific state and asserting the derived state.

When ``task_id`` is ``None`` the Celery lookups short-circuit to ``NOTRUN``
without contacting the broker, so these tests are fast and broker-independent.
The final test additionally runs a workflow for real (Celery eager mode) to
cover the success path end-to-end.
"""

import datetime

import pytest
from django.utils import timezone

from topobank.analysis.models import WorkflowResult
from topobank.analysis.tasks import perform_analysis
from topobank.manager.models import Topography
from topobank.testing.factories import TopographyAnalysisFactory

# Importing this module runs the @register_implementation decorators that make
# the "topobank.testing.test" workflow available. Without it the end-to-end
# eager-execution test only passes when another test happens to import it first.
import topobank.testing.workflows  # noqa: E402,F401


def _make_analysis(test_workflow, **overrides):
    """Create a WorkflowResult without evaluating the workflow.

    ``result=None`` and an explicit ``kwargs`` keep the factory from invoking
    the workflow implementation, so we can control the task fields directly.
    """
    params = dict(
        workflow_name=test_workflow.name,
        kwargs=dict(a=1, b="hamming"),
        result=None,
    )
    params.update(overrides)
    return TopographyAnalysisFactory.create(**params)


# ---------------------------------------------------------------------------
# get_celery_state / get_task_state reconciliation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_self_reported_success_is_trusted(test_workflow):
    a = _make_analysis(test_workflow, task_state=WorkflowResult.SUCCESS, task_id=None)
    # Terminal state -> returned directly without consulting Celery.
    assert a.get_celery_state() == WorkflowResult.SUCCESS
    assert a.get_task_state() == WorkflowResult.SUCCESS
    assert a.get_task_progress() == 100.0
    assert a.get_task_messages() == []


@pytest.mark.django_db
def test_self_reported_failure_is_trusted(test_workflow):
    a = _make_analysis(test_workflow, task_state=WorkflowResult.FAILURE, task_id=None)
    assert a.get_celery_state() == WorkflowResult.FAILURE
    assert a.get_task_state() == WorkflowResult.FAILURE
    assert a.get_task_progress() is None
    assert a.get_task_messages() == []


@pytest.mark.django_db
def test_pending_without_submission_time_is_failure(test_workflow):
    # PENDING in the DB but Celery never saw the task and there is no submission
    # timestamp -> the on-commit hook never fired, treat as failure.
    a = _make_analysis(test_workflow, task_state=WorkflowResult.PENDING, task_id=None)
    a.task_submission_time = None
    assert a.get_celery_state() == WorkflowResult.NOTRUN
    assert a.get_task_state() == WorkflowResult.FAILURE


@pytest.mark.django_db
def test_pending_with_stale_submission_time_is_failure(test_workflow):
    # Submitted longer ago than COMMIT_EXPIRATION but Celery never ran it -> failure.
    a = _make_analysis(test_workflow, task_state=WorkflowResult.PENDING, task_id=None)
    a.task_submission_time = timezone.now() - datetime.timedelta(
        seconds=WorkflowResult.COMMIT_EXPIRATION + 10
    )
    assert a.get_task_state() == WorkflowResult.FAILURE


@pytest.mark.django_db
def test_pending_with_recent_submission_time_stays_pending(test_workflow):
    # Submitted just now: the on-commit task may still be about to start.
    a = _make_analysis(test_workflow, task_state=WorkflowResult.PENDING, task_id=None)
    a.task_submission_time = timezone.now()
    assert a.get_task_state() == WorkflowResult.PENDING


@pytest.mark.django_db
def test_started_without_task_id_falls_back_to_self_report(test_workflow):
    # Non-terminal, non-PENDING self report disagreeing with Celery's NOTRUN
    # -> trust the self-reported state.
    a = _make_analysis(test_workflow, task_state=WorkflowResult.STARTED, task_id=None)
    assert a.get_celery_state() == WorkflowResult.NOTRUN
    assert a.get_task_state() == WorkflowResult.STARTED


# ---------------------------------------------------------------------------
# set_pending_state / get_task_error / task_duration
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_set_pending_state_resets_task_fields(test_workflow):
    a = _make_analysis(test_workflow, task_state=WorkflowResult.SUCCESS)
    a.task_error = "boom"
    a.save()

    a.set_pending_state()

    a.refresh_from_db()
    assert a.task_state == WorkflowResult.PENDING
    assert a.task_id is None
    assert a.task_error == ""
    assert a.task_traceback is None
    assert a.task_submission_time is not None


@pytest.mark.django_db
def test_get_task_error_returns_self_reported_error(test_workflow):
    a = _make_analysis(test_workflow, task_state=WorkflowResult.FAILURE, task_id=None)
    a.task_error = "explicit error message"
    assert a.get_task_error() == "explicit error message"


@pytest.mark.django_db
def test_get_task_error_is_none_without_error_or_tasks(test_workflow):
    a = _make_analysis(test_workflow, task_state=WorkflowResult.SUCCESS, task_id=None)
    a.task_error = ""
    assert a.get_task_error() is None


@pytest.mark.django_db
def test_task_duration(test_workflow):
    a = _make_analysis(test_workflow)
    a.task_start_time = timezone.now() - datetime.timedelta(seconds=5)
    a.task_end_time = timezone.now()
    assert a.task_duration is not None
    assert a.task_duration.total_seconds() >= 4

    # Not finished yet -> no duration.
    a.task_end_time = None
    assert a.task_duration is None


# ---------------------------------------------------------------------------
# End-to-end via Celery eager mode
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_eager_execution_reaches_success(two_topos, test_workflow):
    topo = Topography.objects.first()
    analysis = TopographyAnalysisFactory.create(
        subject_topography=topo,
        workflow_name=test_workflow.name,
        kwargs=dict(a=1, b="hamming"),
        result=None,
        task_state=WorkflowResult.PENDING,
    )
    analysis.save()

    perform_analysis(analysis.id, False)

    analysis.refresh_from_db()
    assert analysis.get_task_state() == WorkflowResult.SUCCESS
    assert analysis.get_task_progress() == 100.0
    assert analysis.get_task_error() is None
    assert analysis.task_duration is not None
