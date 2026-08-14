"""
Functional tests for the analysis custodian (``topobank.analysis.custodian``).

The ``periodic_cleanup`` task does three things:

1. Hard-deletes deprecated, unnamed analysis results that have a subject and
   whose ``deprecation_time`` is older than ``TOPOBANK_ANALYSIS_DELETE_DELAY``.
2. Hard-deletes soft-deleted analysis results whose ``deleted_at`` is older
   than ``TOPOBANK_DELETE_DELAY`` — regardless of ``name`` or subject links.
3. Marks analysis results that are stuck in the ``PENDING`` state (no Celery
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
        - settings.TOPOBANK_ANALYSIS_DELETE_DELAY
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
        - settings.TOPOBANK_ANALYSIS_DELETE_DELAY
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
        - settings.TOPOBANK_ANALYSIS_DELETE_DELAY
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
# Cleanup of soft-deleted results
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_deletes_long_soft_deleted_result():
    analysis = TopographyAnalysisFactory()
    _set_unmanaged_fields(
        analysis,
        deleted_at=timezone.now()
        - settings.TOPOBANK_DELETE_DELAY
        - datetime.timedelta(days=1),
    )

    periodic_cleanup()

    assert not WorkflowResult.objects.filter(pk=analysis.pk).exists()


@pytest.mark.django_db
def test_keeps_recently_soft_deleted_result():
    # Soft-deleted, but still inside the retention window -> restorable.
    analysis = TopographyAnalysisFactory()
    _set_unmanaged_fields(
        analysis,
        deleted_at=timezone.now()
        - settings.TOPOBANK_DELETE_DELAY
        + datetime.timedelta(days=1),
    )

    periodic_cleanup()

    assert WorkflowResult.objects.filter(pk=analysis.pk).exists()


@pytest.mark.django_db
def test_deletes_long_soft_deleted_named_result():
    # Unlike the deprecation clause, a name does not protect a soft-deleted
    # result: it was stamped because its container was deleted, and it goes
    # when the container's retention window closes.
    analysis = TopographyAnalysisFactory(name="my-saved-analysis")
    _set_unmanaged_fields(
        analysis,
        deleted_at=timezone.now()
        - settings.TOPOBANK_DELETE_DELAY
        - datetime.timedelta(days=1),
    )

    periodic_cleanup()

    assert not WorkflowResult.objects.filter(pk=analysis.pk).exists()


@pytest.mark.django_db
def test_deletes_long_soft_deleted_result_without_subject():
    # The deprecation clause requires a surviving subject link; the
    # soft-delete clause must not, or purged containers would strand their
    # results forever.
    analysis = TopographyAnalysisFactory()
    _set_unmanaged_fields(
        analysis,
        subject_topography=None,
        deleted_at=timezone.now()
        - settings.TOPOBANK_DELETE_DELAY
        - datetime.timedelta(days=1),
    )

    periodic_cleanup()

    assert not WorkflowResult.objects.filter(pk=analysis.pk).exists()


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


# ---------------------------------------------------------------------------
# RESTRICT tolerance
# ---------------------------------------------------------------------------


def test_delete_tolerating_restrict_falls_back_to_per_row_and_skips_protected():
    from unittest.mock import MagicMock

    from django.db.models import RestrictedError

    from topobank.analysis.custodian import _delete_tolerating_restrict

    collectable = MagicMock()
    protected = MagicMock()
    protected.delete.side_effect = RestrictedError("protected", set())

    queryset = MagicMock()
    queryset.delete.side_effect = RestrictedError("protected", set())
    queryset.iterator.return_value = iter([collectable, protected])

    _delete_tolerating_restrict(queryset, "analysis results")

    collectable.delete.assert_called_once()
    protected.delete.assert_called_once()


def test_delete_tolerating_restrict_bulk_deletes_when_nothing_is_protected():
    from unittest.mock import MagicMock

    from topobank.analysis.custodian import _delete_tolerating_restrict

    queryset = MagicMock()

    _delete_tolerating_restrict(queryset, "analysis results")

    queryset.delete.assert_called_once()
    queryset.iterator.assert_not_called()
