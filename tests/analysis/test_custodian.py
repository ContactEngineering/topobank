"""
Functional tests for the analysis custodian (``topobank.analysis.custodian``).

The ``periodic_cleanup`` task does two things:

1. Hard-deletes deprecated, unnamed analysis results that have a subject and
   whose ``deprecation_time`` is older than ``TOPOBANK_DELETE_DELAY``.
2. Marks analysis results that are stuck in the ``PENDING`` state (no Celery
   task id) for more than a day as ``FAILURE``.

These tests assert the actual state transitions / deletions, including the
boundary cases that must be left untouched.
"""

import datetime
import uuid

import pytest
from django.conf import settings
from django.utils import timezone

from topobank.analysis.custodian import periodic_cleanup
from topobank.analysis.models import WorkflowResult
from topobank.testing.factories import TopographyAnalysisFactory


def _set_unmanaged_fields(analysis, **fields):
    """Write fields that the ORM manages automatically (e.g. ``created_at``).

    ``queryset.update`` bypasses ``auto_now_add`` so we can backdate timestamps.
    """
    WorkflowResult.objects.filter(pk=analysis.pk).update(**fields)
    analysis.refresh_from_db()


# ---------------------------------------------------------------------------
# Cleanup of deprecated, unnamed results
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_deletes_long_deprecated_unnamed_result_with_subject():
    analysis = TopographyAnalysisFactory()
    assert analysis.name is None
    assert analysis.subject_topography is not None

    _set_unmanaged_fields(
        analysis,
        deprecation_time=timezone.now()
        - settings.TOPOBANK_DELETE_DELAY
        - datetime.timedelta(days=1),
    )

    periodic_cleanup()

    assert not WorkflowResult.objects.filter(pk=analysis.pk).exists()


@pytest.mark.django_db
def test_keeps_recently_deprecated_result():
    # Deprecated, but still inside the grace period -> must survive.
    analysis = TopographyAnalysisFactory()
    _set_unmanaged_fields(
        analysis,
        deprecation_time=timezone.now()
        - settings.TOPOBANK_DELETE_DELAY
        + datetime.timedelta(days=1),
    )

    periodic_cleanup()

    assert WorkflowResult.objects.filter(pk=analysis.pk).exists()


@pytest.mark.django_db
def test_keeps_named_result_even_if_long_deprecated():
    # A named result is a saved/user-facing result and must never be auto-deleted.
    analysis = TopographyAnalysisFactory(name="my-saved-analysis")
    _set_unmanaged_fields(
        analysis,
        deprecation_time=timezone.now()
        - settings.TOPOBANK_DELETE_DELAY
        - datetime.timedelta(days=1),
    )

    periodic_cleanup()

    assert WorkflowResult.objects.filter(pk=analysis.pk).exists()


@pytest.mark.django_db
def test_keeps_active_non_deprecated_result():
    # deprecation_time is NULL -> active result, never eligible for cleanup.
    analysis = TopographyAnalysisFactory()
    assert analysis.deprecation_time is None

    periodic_cleanup()

    assert WorkflowResult.objects.filter(pk=analysis.pk).exists()


# ---------------------------------------------------------------------------
# Failing results stuck in the PENDING state
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_marks_stuck_pending_result_as_failure():
    analysis = TopographyAnalysisFactory(
        task_state=WorkflowResult.PENDING, task_id=None
    )
    _set_unmanaged_fields(
        analysis, created_at=timezone.now() - datetime.timedelta(days=2)
    )

    periodic_cleanup()

    analysis.refresh_from_db()
    assert analysis.task_state == WorkflowResult.FAILURE
    assert analysis.task_error == "Analysis failed to launch."
    # It must not be deleted, only updated.
    assert WorkflowResult.objects.filter(pk=analysis.pk).exists()


@pytest.mark.django_db
def test_keeps_recent_pending_result():
    # Pending for less than a day -> give it more time, leave untouched.
    analysis = TopographyAnalysisFactory(
        task_state=WorkflowResult.PENDING, task_id=None
    )

    periodic_cleanup()

    analysis.refresh_from_db()
    assert analysis.task_state == WorkflowResult.PENDING


@pytest.mark.django_db
def test_keeps_pending_result_that_has_a_task_id():
    # A task id means the task was actually dispatched -> not "stuck".
    analysis = TopographyAnalysisFactory(
        task_state=WorkflowResult.PENDING, task_id=uuid.uuid4()
    )
    _set_unmanaged_fields(
        analysis, created_at=timezone.now() - datetime.timedelta(days=2)
    )

    periodic_cleanup()

    analysis.refresh_from_db()
    assert analysis.task_state == WorkflowResult.PENDING


@pytest.mark.django_db
def test_cleanup_on_empty_database_is_noop():
    periodic_cleanup()
    assert WorkflowResult.objects.count() == 0
