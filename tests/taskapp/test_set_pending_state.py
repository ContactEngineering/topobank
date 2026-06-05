"""
Unit tests for TaskStateModel.set_pending_state in taskapp/models.py

Re-pending a task (e.g. when a dependency is recomputed) must reset the row so
it looks freshly created. In particular the timestamps from any prior run have
to be cleared, otherwise task_duration reports garbage and a stale
task_start_time could be mistaken for an in-flight run.
"""
import datetime

import pytest

from topobank.analysis.models import WorkflowResult
from topobank.testing.factories import TopographyAnalysisFactory


@pytest.mark.django_db
class TestSetPendingState:
    """Tests for TaskStateModel.set_pending_state"""

    def test_clears_timestamps(self, test_workflow):
        """Both run timestamps are reset so the re-pended row looks fresh."""
        analysis = TopographyAnalysisFactory(
            task_state=WorkflowResult.SUCCESS,
            task_start_time=datetime.datetime(2018, 1, 1, 12),
            task_end_time=datetime.datetime(2018, 1, 1, 13),
            workflow_name=test_workflow.name,
        )

        analysis.set_pending_state()

        assert analysis.task_start_time is None
        assert analysis.task_end_time is None

        # ...and the reset is persisted, not just held in memory.
        analysis.refresh_from_db()
        assert analysis.task_start_time is None
        assert analysis.task_end_time is None

    def test_task_duration_is_none_after_repend(self, test_workflow):
        """duration() must not report a stale value from the previous run."""
        analysis = TopographyAnalysisFactory(
            task_state=WorkflowResult.SUCCESS,
            task_start_time=datetime.datetime(2018, 1, 1, 12),
            task_end_time=datetime.datetime(2018, 1, 1, 13),
            workflow_name=test_workflow.name,
        )
        # Sanity check: the analysis has a duration before re-pending.
        assert analysis.task_duration == datetime.timedelta(hours=1)

        analysis.set_pending_state()

        assert analysis.task_duration is None

    def test_resets_state_and_clears_error_fields(self, test_workflow):
        """The remaining bookkeeping fields are reset alongside the timestamps."""
        analysis = TopographyAnalysisFactory(
            task_state=WorkflowResult.FAILURE,
            task_id="some-stale-celery-id",
            task_error="boom",
            task_traceback="Traceback (most recent call last): ...",
            workflow_name=test_workflow.name,
        )

        analysis.set_pending_state()
        analysis.refresh_from_db()

        assert analysis.task_state == WorkflowResult.PENDING
        assert analysis.task_id is None
        assert analysis.task_error == ""
        assert analysis.task_traceback is None
        assert analysis.task_submission_time is not None

    def test_autosave_false_does_not_persist(self, test_workflow):
        """With autosave=False the in-memory row is reset but the DB is untouched."""
        analysis = TopographyAnalysisFactory(
            task_state=WorkflowResult.SUCCESS,
            task_start_time=datetime.datetime(2018, 1, 1, 12),
            task_end_time=datetime.datetime(2018, 1, 1, 13),
            workflow_name=test_workflow.name,
        )

        analysis.set_pending_state(autosave=False)

        # In-memory instance reflects the reset...
        assert analysis.task_start_time is None
        assert analysis.task_end_time is None
        assert analysis.task_state == WorkflowResult.PENDING

        # ...but nothing was written, so the database still has the old values.
        analysis.refresh_from_db()
        assert analysis.task_start_time is not None
        assert analysis.task_end_time is not None
        assert analysis.task_state == WorkflowResult.SUCCESS
