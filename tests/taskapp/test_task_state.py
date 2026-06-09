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
import uuid
from types import SimpleNamespace

import celery.states
import pytest
from django.test import override_settings
from django.utils import timezone
from SurfaceTopography.Exceptions import CannotDetectFileFormat

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


# ---------------------------------------------------------------------------
# Celery result caching helpers (_get_result_state / _get_result_info)
#
# These are tested with a stub AsyncResult and a deterministic local-memory
# cache, so they do not depend on a running broker. Calling them twice exercises
# both the cache-miss (query + store) and cache-hit (return stored) paths.
# ---------------------------------------------------------------------------


@override_settings(
    CACHES={
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    }
)
@pytest.mark.django_db
def test_get_result_state_is_cached(test_workflow):
    from django.core.cache import cache

    cache.clear()
    a = _make_analysis(test_workflow)
    r = SimpleNamespace(id=uuid.uuid4(), state="PROGRESS", info={"current": 1})

    assert a._get_result_state(r) == "PROGRESS"  # miss -> query + cache
    r.state = "SUCCESS"
    assert a._get_result_state(r) == "PROGRESS"  # hit -> stale cached value


@override_settings(
    CACHES={
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    }
)
@pytest.mark.django_db
def test_get_result_info_is_cached(test_workflow):
    from django.core.cache import cache

    cache.clear()
    a = _make_analysis(test_workflow)
    r = SimpleNamespace(id=uuid.uuid4(), state="PROGRESS", info={"current": 1})

    assert a._get_result_info(r) == {"current": 1}  # miss -> query + cache
    r.info = {"current": 99}
    assert a._get_result_info(r) == {"current": 1}  # hit -> stale cached value


@pytest.mark.django_db
def test_result_helpers_handle_none(test_workflow):
    a = _make_analysis(test_workflow)
    assert a._get_result_state(None) is None
    assert a._get_result_info(None) is None


# ---------------------------------------------------------------------------
# get_celery_state / get_task_state with injected Celery results
#
# Eager mode never yields STARTED / PROGRESS / FAILURE AsyncResult states, so we
# inject them at the seams (get_async_result(s) / _get_result_state) and assert
# the reconciliation logic on top.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_celery_state_failure_from_dependent_task(mocker, test_workflow):
    a = _make_analysis(test_workflow, task_state=WorkflowResult.STARTED, task_id=None)
    mocker.patch.object(a, "get_async_results", return_value=[mocker.Mock()])
    mocker.patch.object(a, "_get_result_state", return_value=celery.states.FAILURE)
    assert a.get_celery_state() == WorkflowResult.FAILURE


@pytest.mark.django_db
def test_celery_state_maps_running_task(mocker, test_workflow):
    a = _make_analysis(
        test_workflow, task_state=WorkflowResult.STARTED, task_id=uuid.uuid4()
    )
    mocker.patch.object(a, "get_async_results", return_value=[])
    mocker.patch.object(a, "get_async_result", return_value=mocker.Mock())
    mocker.patch.object(a, "_get_result_state", return_value=celery.states.STARTED)
    assert a.get_celery_state() == WorkflowResult.STARTED


@pytest.mark.django_db
def test_celery_state_unknown_state_is_started(mocker, test_workflow):
    a = _make_analysis(
        test_workflow, task_state=WorkflowResult.STARTED, task_id=uuid.uuid4()
    )
    mocker.patch.object(a, "get_async_results", return_value=[])
    mocker.patch.object(a, "get_async_result", return_value=mocker.Mock())
    # A custom Celery state (e.g. 'PROGRESS') is not in the state map.
    mocker.patch.object(a, "_get_result_state", return_value="PROGRESS")
    assert a.get_celery_state() == WorkflowResult.STARTED


@pytest.mark.django_db
def test_task_state_agrees_with_celery(mocker, test_workflow):
    a = _make_analysis(test_workflow, task_state=WorkflowResult.STARTED, task_id=None)
    mocker.patch.object(a, "get_celery_state", return_value=WorkflowResult.STARTED)
    assert a.get_task_state() == WorkflowResult.STARTED


@pytest.mark.django_db
def test_task_state_celery_failure_overrides_self_report(mocker, test_workflow):
    a = _make_analysis(test_workflow, task_state=WorkflowResult.STARTED, task_id=None)
    mocker.patch.object(a, "get_celery_state", return_value=WorkflowResult.FAILURE)
    assert a.get_task_state() == WorkflowResult.FAILURE


# ---------------------------------------------------------------------------
# get_task_progress / get_task_messages aggregation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_task_progress_aggregates_children(mocker, test_workflow):
    a = _make_analysis(test_workflow, task_state=WorkflowResult.STARTED, task_id=None)
    mocker.patch.object(
        a, "get_async_results", return_value=[mocker.Mock(), mocker.Mock()]
    )
    # One finished child, one half-way child -> (1 + 0.5) / 2 = 75 %.
    mocker.patch.object(
        a, "_get_result_state", side_effect=[celery.states.SUCCESS, "PROGRESS"]
    )
    mocker.patch.object(
        a,
        "_get_result_info",
        side_effect=[None, {"current": 5.0, "total": 10.0, "message": "half"}],
    )
    assert a.get_task_progress() == 75.0


@pytest.mark.django_db
def test_task_progress_counts_pending_and_ignores_invalid(mocker, test_workflow):
    a = _make_analysis(test_workflow, task_state=WorkflowResult.STARTED, task_id=None)
    mocker.patch.object(
        a,
        "get_async_results",
        return_value=[mocker.Mock(), mocker.Mock(), mocker.Mock()],
    )
    # A pending child contributes to the total but not to progress; the two
    # malformed progress payloads (validation error, then non-mapping) are
    # ignored entirely.
    mocker.patch.object(
        a, "_get_result_state", side_effect=[celery.states.PENDING, "PROGRESS", "PROGRESS"]
    )
    mocker.patch.object(
        a, "_get_result_info", side_effect=[None, {"current": "x"}, "junk"]
    )
    assert a.get_task_progress() == 0.0


@pytest.mark.django_db
def test_get_async_results_uses_cache(test_workflow):
    a = _make_analysis(test_workflow)
    sentinel = [object()]
    a._cached_async_results = sentinel
    assert a.get_async_results() is sentinel


@pytest.mark.django_db
def test_task_progress_returns_none_on_failure(mocker, test_workflow):
    a = _make_analysis(test_workflow, task_state=WorkflowResult.STARTED, task_id=None)
    mocker.patch.object(a, "get_async_results", return_value=[mocker.Mock()])
    mocker.patch.object(a, "_get_result_state", side_effect=[celery.states.FAILURE])
    mocker.patch.object(a, "_get_result_info", side_effect=[None])
    assert a.get_task_progress() is None


@pytest.mark.django_db
def test_task_messages_collects_progress_messages(mocker, test_workflow):
    a = _make_analysis(test_workflow, task_state=WorkflowResult.STARTED, task_id=None)
    mocker.patch.object(a, "get_async_results", return_value=[mocker.Mock()])
    mocker.patch.object(a, "_get_result_state", side_effect=["PROGRESS"])
    mocker.patch.object(
        a,
        "_get_result_info",
        side_effect=[{"current": 1.0, "total": 2.0, "message": "working"}],
    )
    assert a.get_task_messages() == ["working"]


@pytest.mark.django_db
def test_task_messages_ignores_invalid_payloads(mocker, test_workflow):
    a = _make_analysis(test_workflow, task_state=WorkflowResult.STARTED, task_id=None)
    mocker.patch.object(
        a, "get_async_results", return_value=[mocker.Mock(), mocker.Mock()]
    )
    mocker.patch.object(a, "_get_result_state", side_effect=["PROGRESS", "PROGRESS"])
    # First payload fails pydantic validation, second is not a mapping (TypeError).
    mocker.patch.object(
        a, "_get_result_info", side_effect=[{"current": "not-a-number"}, "junk"]
    )
    assert a.get_task_messages() == []


@pytest.mark.django_db
def test_task_messages_returns_none_on_failure(mocker, test_workflow):
    a = _make_analysis(test_workflow, task_state=WorkflowResult.STARTED, task_id=None)
    mocker.patch.object(a, "get_async_results", return_value=[mocker.Mock()])
    mocker.patch.object(a, "_get_result_state", side_effect=[celery.states.REVOKED])
    mocker.patch.object(a, "_get_result_info", side_effect=[None])
    assert a.get_task_messages() is None


# ---------------------------------------------------------------------------
# get_task_error derived from a Celery exception
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_task_error_from_celery_exception(mocker, test_workflow):
    a = _make_analysis(test_workflow, task_state=WorkflowResult.STARTED, task_id=None)
    a.task_error = ""
    a.save(update_fields=["task_error"])
    mocker.patch.object(a, "get_async_results", return_value=[mocker.Mock()])
    mocker.patch.object(a, "_get_result_info", return_value=ValueError("kaboom"))

    assert "kaboom" in a.get_task_error()

    # The failure is persisted for future reference.
    a.refresh_from_db()
    assert a.task_state == WorkflowResult.FAILURE
    assert a.task_error == "kaboom"


# ---------------------------------------------------------------------------
# run_task: success-with-timer, CannotDetectFileFormat, and generic failure
# ---------------------------------------------------------------------------


def _fake_celery_task():
    return SimpleNamespace(request=SimpleNamespace(id=str(uuid.uuid4())))


@pytest.mark.django_db
def test_run_task_success_with_timer(test_workflow):
    a = _make_analysis(test_workflow, task_state=WorkflowResult.PENDING)

    def worker(*args, timer=None, **kwargs):
        # A worker that accepts `timer` exercises the timing branch.
        pass

    a.task_worker = worker
    a.run_task(_fake_celery_task())

    a.refresh_from_db()
    assert a.task_state == WorkflowResult.SUCCESS
    assert a.task_error == ""
    assert a.task_timer is not None


@pytest.mark.django_db
def test_run_task_cannot_detect_file_format(test_workflow):
    a = _make_analysis(test_workflow, task_state=WorkflowResult.PENDING)

    def worker(*args, **kwargs):
        raise CannotDetectFileFormat("unknown format")

    a.task_worker = worker
    # This failure mode is handled, not re-raised.
    a.run_task(_fake_celery_task())

    a.refresh_from_db()
    assert a.task_state == WorkflowResult.FAILURE
    assert "unknown or unsupported format" in a.task_error


@pytest.mark.django_db
def test_run_task_generic_exception_is_recorded_and_reraised(test_workflow):
    a = _make_analysis(test_workflow, task_state=WorkflowResult.PENDING)

    def worker(*args, **kwargs):
        raise ValueError("boom")

    a.task_worker = worker
    with pytest.raises(ValueError):
        a.run_task(_fake_celery_task())

    a.refresh_from_db()
    assert a.task_state == WorkflowResult.FAILURE
    assert a.task_error == "boom"
    assert a.task_traceback


# ---------------------------------------------------------------------------
# cancel_task
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_cancel_task_revokes_running_task(mocker, test_workflow):
    a = _make_analysis(test_workflow, task_state=WorkflowResult.STARTED)
    result = mocker.Mock()
    mocker.patch.object(a, "get_async_result", return_value=result)

    a.cancel_task()

    result.revoke.assert_called_once()
