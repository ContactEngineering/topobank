"""
Unit tests for Celery signal handlers in taskapp/celeryapp.py

Tests the automatic task state synchronization handlers:
- handle_task_failure: Catches worker crashes, timeouts, OOM kills
- handle_task_revoked: Catches task cancellations and revocations
- handle_task_success: Validates state consistency
- _find_task_instance: Helper to locate TaskStateModel instances
"""
import uuid
from unittest.mock import Mock

import pytest
from celery.signals import task_failure, task_revoked, task_success
from django.utils import timezone

from topobank.analysis.models import WorkflowResult
from topobank.manager.models import Topography
from topobank.manager.zip_model import ZipContainer
from topobank.taskapp.celeryapp import CeleryAppConfig
from topobank.testing.factories import (
    SurfaceFactory,
    Topography2DFactory,
    TopographyAnalysisFactory,
    UserFactory,
)


@pytest.fixture
def app_config():
    """Get the registered CeleryAppConfig instance."""
    from django.apps import apps
    return apps.get_app_config("taskapp")


@pytest.fixture
def mock_now(mocker):
    """Mock timezone.now() to return a fixed datetime."""
    fixed_time = timezone.now()
    mocker.patch("topobank.taskapp.celeryapp.timezone.now", return_value=fixed_time)
    return fixed_time


@pytest.mark.django_db
class TestTaskFailureSignal:
    """Tests for handle_task_failure signal handler"""

    def test_updates_state_on_worker_crash(self, app_config, mock_now, test_analysis_function):
        """Test that task failure updates state from STARTED to FAILURE."""
        task_id = str(uuid.uuid4())
        analysis = TopographyAnalysisFactory(
            task_state=WorkflowResult.STARTED,
            task_id=task_id,
            function=test_analysis_function,
        )

        # Send task_failure signal
        task_failure.send(
            sender=None,
            task_id=task_id,
            exception=Exception("Worker crashed"),
            traceback="Traceback here",
        )

        # Verify state was updated
        analysis.refresh_from_db()
        assert analysis.task_state == WorkflowResult.FAILURE
        assert analysis.task_error == "Worker crashed"
        assert analysis.task_traceback == "Traceback here"
        assert analysis.task_end_time == mock_now

    def test_records_exception_message_and_traceback(self, app_config, mock_now, test_analysis_function):
        """Test that exception details are properly recorded."""
        task_id = str(uuid.uuid4())
        analysis = TopographyAnalysisFactory(
            task_state=WorkflowResult.STARTED,
            task_id=task_id,
            function=test_analysis_function,
        )

        exception_msg = "Out of memory error"
        traceback_msg = "Traceback (most recent call last):\n  File 'worker.py', line 42"

        task_failure.send(
            sender=None,
            task_id=task_id,
            exception=Exception(exception_msg),
            traceback=traceback_msg,
        )

        analysis.refresh_from_db()
        assert analysis.task_error == exception_msg
        assert analysis.task_traceback == traceback_msg

    def test_sets_task_end_time(self, app_config, mock_now, test_analysis_function):
        """Test that task_end_time is set when task fails."""
        task_id = str(uuid.uuid4())
        analysis = TopographyAnalysisFactory(
            task_state=WorkflowResult.STARTED,
            task_id=task_id,
            task_end_time=None,
            function=test_analysis_function,
        )

        task_failure.send(
            sender=None,
            task_id=task_id,
            exception=Exception("Timeout"),
            traceback="",
        )

        analysis.refresh_from_db()
        assert analysis.task_end_time == mock_now

    def test_respects_success_terminal_state(self, app_config, mocker, test_analysis_function):
        """Test that SUCCESS state is not overridden by failure signal."""
        task_id = str(uuid.uuid4())
        analysis = TopographyAnalysisFactory(
            task_state=WorkflowResult.SUCCESS,
            task_id=task_id,
            function=test_analysis_function,
        )

        # Mock save to verify it's not called
        save_spy = mocker.spy(WorkflowResult, "save")

        task_failure.send(
            sender=None,
            task_id=task_id,
            exception=Exception("Late failure"),
            traceback="",
        )

        analysis.refresh_from_db()
        assert analysis.task_state == WorkflowResult.SUCCESS
        # save should not have been called for this instance
        assert save_spy.call_count == 0

    def test_respects_failure_terminal_state(self, app_config, mocker, test_analysis_function):
        """Test that FAILURE state is not overridden by another failure signal."""
        task_id = str(uuid.uuid4())
        original_error = "Original error"
        analysis = TopographyAnalysisFactory(
            task_state=WorkflowResult.FAILURE,
            task_id=task_id,
            task_error=original_error,
            function=test_analysis_function,
        )

        # Mock save to verify it's not called
        save_spy = mocker.spy(WorkflowResult, "save")

        task_failure.send(
            sender=None,
            task_id=task_id,
            exception=Exception("Second failure"),
            traceback="",
        )

        analysis.refresh_from_db()
        assert analysis.task_state == WorkflowResult.FAILURE
        assert analysis.task_error == original_error  # Unchanged
        assert save_spy.call_count == 0

    def test_handles_missing_task_id_gracefully(self, app_config, mocker, test_analysis_function):
        """Test that signal handler doesn't crash when task_id is not found."""
        # Mock logger to verify debug message
        mock_log = mocker.patch("topobank.taskapp.celeryapp._log")

        # Send signal with non-existent task_id
        task_failure.send(
            sender=None,
            task_id="non-existent-task-id",
            exception=Exception("Error"),
            traceback="",
        )

        # Should log debug message but not crash
        assert mock_log.debug.called

    def test_handles_all_model_types(self, app_config, mock_now, test_analysis_function):
        """Test that signal handler works for WorkflowResult, Topography, and ZipContainer."""
        # Test WorkflowResult
        task_id_1 = str(uuid.uuid4())
        analysis = TopographyAnalysisFactory(
            task_state=WorkflowResult.STARTED,
            task_id=task_id_1,
            function=test_analysis_function,
        )

        task_failure.send(
            sender=None,
            task_id=task_id_1,
            exception=Exception("Error 1"),
            traceback="",
        )

        analysis.refresh_from_db()
        assert analysis.task_state == WorkflowResult.FAILURE

        # Test Topography
        task_id_2 = str(uuid.uuid4())
        user = UserFactory()
        surface = SurfaceFactory(created_by=user)
        topo = Topography2DFactory(
            surface=surface,
            task_state=Topography.STARTED,
            task_id=task_id_2,
        )

        task_failure.send(
            sender=None,
            task_id=task_id_2,
            exception=Exception("Error 2"),
            traceback="",
        )

        topo.refresh_from_db()
        assert topo.task_state == Topography.FAILURE

        # Test ZipContainer
        task_id_3 = str(uuid.uuid4())
        from topobank.authorization.models import PermissionSet
        permissions = PermissionSet.objects.create()
        permissions.grant(user, "edit")
        zip_container = ZipContainer.objects.create(
            permissions=permissions,
            task_state=ZipContainer.STARTED,
            task_id=task_id_3,
        )

        task_failure.send(
            sender=None,
            task_id=task_id_3,
            exception=Exception("Error 3"),
            traceback="",
        )

        zip_container.refresh_from_db()
        assert zip_container.task_state == ZipContainer.FAILURE

    def test_signal_handler_exception_handling(self, app_config, mocker, test_analysis_function):
        """Test that signal handler doesn't crash even if internal error occurs."""
        task_id = str(uuid.uuid4())
        TopographyAnalysisFactory(
            task_state=WorkflowResult.STARTED,
            task_id=task_id,
            function=test_analysis_function,
        )

        # Mock save to raise an exception
        mock_log = mocker.patch("topobank.taskapp.celeryapp._log")
        mocker.patch.object(WorkflowResult, "save", side_effect=Exception("DB error"))

        # Should not raise exception
        task_failure.send(
            sender=None,
            task_id=task_id,
            exception=Exception("Original error"),
            traceback="",
        )

        # Should log error
        assert mock_log.error.called


@pytest.mark.django_db
class TestTaskRevokedSignal:
    """Tests for handle_task_revoked signal handler"""

    def test_updates_state_on_cancellation(self, app_config, mock_now, test_analysis_function):
        """Test that task revocation updates state to FAILURE."""
        task_id = str(uuid.uuid4())
        analysis = TopographyAnalysisFactory(
            task_state=WorkflowResult.STARTED,
            task_id=task_id,
            function=test_analysis_function,
        )

        # Create mock request object
        mock_request = Mock()
        mock_request.id = task_id

        task_revoked.send(
            sender=None,
            request=mock_request,
            terminated=False,
            signum=None,
            expired=False,
        )

        analysis.refresh_from_db()
        assert analysis.task_state == WorkflowResult.FAILURE
        assert "cancelled" in analysis.task_error.lower()
        assert analysis.task_end_time == mock_now

    def test_records_terminated_flag(self, app_config, mock_now, test_analysis_function):
        """Test that terminated flag is recorded in error message."""
        task_id = str(uuid.uuid4())
        analysis = TopographyAnalysisFactory(
            task_state=WorkflowResult.STARTED,
            task_id=task_id,
            function=test_analysis_function,
        )

        mock_request = Mock()
        mock_request.id = task_id

        task_revoked.send(
            sender=None,
            request=mock_request,
            terminated=True,
            signum=9,
            expired=False,
        )

        analysis.refresh_from_db()
        assert analysis.task_state == WorkflowResult.FAILURE
        assert "terminated" in analysis.task_error.lower()

    def test_records_expired_flag(self, app_config, mock_now, test_analysis_function):
        """Test that expired flag is recorded in error message."""
        task_id = str(uuid.uuid4())
        analysis = TopographyAnalysisFactory(
            task_state=WorkflowResult.STARTED,
            task_id=task_id,
            function=test_analysis_function,
        )

        mock_request = Mock()
        mock_request.id = task_id

        task_revoked.send(
            sender=None,
            request=mock_request,
            terminated=False,
            signum=None,
            expired=True,
        )

        analysis.refresh_from_db()
        assert analysis.task_state == WorkflowResult.FAILURE
        assert "expired" in analysis.task_error.lower()

    def test_sets_task_end_time(self, app_config, mock_now, test_analysis_function):
        """Test that task_end_time is set when task is revoked."""
        task_id = str(uuid.uuid4())
        analysis = TopographyAnalysisFactory(
            task_state=WorkflowResult.STARTED,
            task_id=task_id,
            task_end_time=None,
            function=test_analysis_function,
        )

        mock_request = Mock()
        mock_request.id = task_id

        task_revoked.send(
            sender=None,
            request=mock_request,
            terminated=False,
            signum=None,
            expired=False,
        )

        analysis.refresh_from_db()
        assert analysis.task_end_time == mock_now

    def test_respects_terminal_states(self, app_config, mocker, test_analysis_function):
        """Test that terminal states are not overridden."""
        task_id = str(uuid.uuid4())
        analysis = TopographyAnalysisFactory(
            task_state=WorkflowResult.SUCCESS,
            task_id=task_id,
            function=test_analysis_function,
        )

        save_spy = mocker.spy(WorkflowResult, "save")

        mock_request = Mock()
        mock_request.id = task_id

        task_revoked.send(
            sender=None,
            request=mock_request,
            terminated=True,
            signum=None,
            expired=False,
        )

        analysis.refresh_from_db()
        assert analysis.task_state == WorkflowResult.SUCCESS
        assert save_spy.call_count == 0

    def test_handles_missing_task_id_gracefully(self, app_config, mocker, test_analysis_function):
        """Test that signal handler doesn't crash when task_id is not found."""
        mock_log = mocker.patch("topobank.taskapp.celeryapp._log")

        # Send signal with request but non-existent task_id
        mock_request = Mock()
        mock_request.id = "non-existent-task-id"

        task_revoked.send(
            sender=None,
            request=mock_request,
            terminated=False,
            signum=None,
            expired=False,
        )

        # Should log debug message but not crash
        assert mock_log.debug.called

    def test_signal_handler_exception_handling(self, app_config, mocker, test_analysis_function):
        """Test that signal handler doesn't crash even if internal error occurs."""
        task_id = str(uuid.uuid4())
        TopographyAnalysisFactory(
            task_state=WorkflowResult.STARTED,
            task_id=task_id,
            function=test_analysis_function,
        )

        mock_log = mocker.patch("topobank.taskapp.celeryapp._log")
        mocker.patch.object(WorkflowResult, "save", side_effect=Exception("DB error"))

        mock_request = Mock()
        mock_request.id = task_id

        # Should not raise exception
        task_revoked.send(
            sender=None,
            request=mock_request,
            terminated=False,
            signum=None,
            expired=False,
        )

        # Should log error
        assert mock_log.error.called


@pytest.mark.django_db
class TestTaskSuccessSignal:
    """Tests for handle_task_success signal handler"""

    def test_logs_warning_on_state_mismatch(self, app_config, mocker, test_analysis_function):
        """Test that warning is logged when Celery reports SUCCESS but DB shows FAILURE."""
        task_id = str(uuid.uuid4())
        TopographyAnalysisFactory(
            task_state=WorkflowResult.FAILURE,
            task_id=task_id,
            function=test_analysis_function,
        )

        mock_log = mocker.patch("topobank.taskapp.celeryapp._log")

        # Create mock sender with request
        mock_sender = Mock()
        mock_sender.request = Mock()
        mock_sender.request.id = task_id

        task_success.send(
            sender=mock_sender,
            result={"status": "success"},
        )

        # Should log warning about mismatch
        assert mock_log.warning.called
        warning_msg = mock_log.warning.call_args[0][0]
        assert "mismatch" in warning_msg.lower()

    def test_no_action_when_states_match(self, app_config, mocker, test_analysis_function):
        """Test that no action is taken when states match."""
        task_id = str(uuid.uuid4())
        TopographyAnalysisFactory(
            task_state=WorkflowResult.SUCCESS,
            task_id=task_id,
            function=test_analysis_function,
        )

        mock_log = mocker.patch("topobank.taskapp.celeryapp._log")

        mock_sender = Mock()
        mock_sender.request = Mock()
        mock_sender.request.id = task_id

        task_success.send(
            sender=mock_sender,
            result={"status": "success"},
        )

        # Should not log warning when states match
        assert not mock_log.warning.called

    def test_handles_missing_task_id_gracefully(self, app_config, mocker, test_analysis_function):
        """Test that signal handler doesn't crash when task_id cannot be extracted."""
        mock_log = mocker.patch("topobank.taskapp.celeryapp._log")

        # Send signal with sender that has no request attribute
        mock_sender = Mock(spec=[])  # No attributes

        # Should not crash
        task_success.send(
            sender=mock_sender,
            result={"status": "success"},
        )

        # Should not log anything since task_id couldn't be extracted
        assert not mock_log.warning.called

    def test_signal_handler_exception_handling(self, app_config, mocker, test_analysis_function):
        """Test that signal handler doesn't crash even if internal error occurs."""
        task_id = str(uuid.uuid4())
        TopographyAnalysisFactory(
            task_state=WorkflowResult.FAILURE,
            task_id=task_id,
            function=test_analysis_function,
        )

        mock_log = mocker.patch("topobank.taskapp.celeryapp._log")

        # Mock _find_task_instance to raise an exception
        mocker.patch.object(
            CeleryAppConfig,
            "_find_task_instance",
            side_effect=Exception("Lookup error")
        )

        mock_sender = Mock()
        mock_sender.request = Mock()
        mock_sender.request.id = task_id

        # Should not raise exception
        task_success.send(
            sender=mock_sender,
            result={"status": "success"},
        )

        # Should log error
        assert mock_log.error.called


@pytest.mark.django_db
class TestFindTaskInstance:
    """Tests for _find_task_instance helper method"""

    def test_finds_workflow_result(self, app_config, test_analysis_function):
        """Test that WorkflowResult can be found by task_id."""
        task_id = str(uuid.uuid4())
        analysis = TopographyAnalysisFactory(
            task_id=task_id,
            function=test_analysis_function,
        )

        found = app_config._find_task_instance(task_id)

        assert found is not None
        assert found.id == analysis.id
        assert isinstance(found, WorkflowResult)

    def test_finds_topography(self, app_config):
        """Test that Topography can be found by task_id."""
        task_id = str(uuid.uuid4())
        user = UserFactory()
        surface = SurfaceFactory(created_by=user)
        topo = Topography2DFactory(
            surface=surface,
            task_id=task_id,
        )

        found = app_config._find_task_instance(task_id)

        assert found is not None
        assert found.id == topo.id
        assert isinstance(found, Topography)

    def test_finds_zip_container(self, app_config):
        """Test that ZipContainer can be found by task_id."""
        task_id = str(uuid.uuid4())
        user = UserFactory()
        from topobank.authorization.models import PermissionSet
        permissions = PermissionSet.objects.create()
        permissions.grant(user, "edit")
        zip_container = ZipContainer.objects.create(
            permissions=permissions,
            task_id=task_id,
        )

        found = app_config._find_task_instance(task_id)

        assert found is not None
        assert found.id == zip_container.id
        assert isinstance(found, ZipContainer)

    def test_returns_none_for_missing_task(self, app_config):
        """Test that None is returned when task_id is not found."""
        result = app_config._find_task_instance("non-existent-task-id")
        assert result is None

    def test_returns_first_match(self, app_config, test_analysis_function):
        """Test that first matching instance is returned when multiple exist."""
        task_id = str(uuid.uuid4())

        # Create WorkflowResult with this task_id
        analysis = TopographyAnalysisFactory(
            task_id=task_id,
            function=test_analysis_function,
        )

        # The helper searches in order: WorkflowResult, Topography, ZipContainer
        # So it should find WorkflowResult first
        found = app_config._find_task_instance(task_id)

        assert found is not None
        assert isinstance(found, WorkflowResult)
        assert found.id == analysis.id
