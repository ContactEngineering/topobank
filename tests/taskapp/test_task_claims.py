"""Tests for claiming a task at dispatch and at the worker.

A measurement is processed once per dispatch: `run_task` claims the row with a
conditional update before anything is sent to Celery, and `task_dispatch` claims
it again for the delivered message before the worker runs. Concurrent callers
race on real transactions here (``transaction=True`` and one database connection
per thread), so the guarantees come from PostgreSQL, not from mocks. Only the
broker is replaced: `apply_async` records the messages instead of running them.
"""

import threading
import time
import uuid
from datetime import timedelta
from unittest import mock

import celery.states
import pytest
from celery.signals import task_success
from django.contrib.contenttypes.models import ContentType
from django.db import connection, transaction
from django.utils import timezone

from topobank.manager.models import Topography
from topobank.taskapp import utils
from topobank.taskapp.models import TaskStateModel
from topobank.taskapp.utils import claim_started, run_task, task_dispatch
from topobank.testing.factories import Topography1DFactory


@pytest.fixture
def broker():
    """Messages sent to Celery, as ``(args, task_id)`` tuples."""
    messages = []
    lock = threading.Lock()

    def apply_async(args=None, kwargs=None, task_id=None, **options):
        with lock:
            messages.append((list(args), task_id))

    with mock.patch.object(task_dispatch, "apply_async", side_effect=apply_async):
        yield messages


def _topography(state=TaskStateModel.SUCCESS, **extra):
    topo = Topography1DFactory()
    Topography.objects.filter(pk=topo.pk).update(task_state=state, **extra)
    topo.refresh_from_db()
    return topo


def _deliver(topo, task_id):
    """Run the message for ``topo`` as a worker would.

    Returns the task result, or None for a delivery the worker ignored.
    """
    ct = ContentType.objects.get_for_model(Topography)
    result = task_dispatch.apply(args=[ct.id, topo.pk], task_id=str(task_id))
    if result.state == celery.states.IGNORED:
        return None
    return result.get()


def _in_threads(nb_threads, func):
    """Run ``func(i)`` in threads released together; each uses its own connection."""
    barrier = threading.Barrier(nb_threads)
    results = [None] * nb_threads
    errors = []

    def worker(i):
        try:
            barrier.wait()
            results[i] = func(i)
        except Exception as exc:  # pragma: no cover - surfaced below
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(nb_threads)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    return results


#
# Claim at dispatch
#


@pytest.mark.django_db(transaction=True)
def test_concurrent_dispatches_claim_exactly_once(broker):
    topo = _topography()
    broker.clear()

    def dispatch(i):
        # Every caller holds its own (stale) copy of the row, as concurrent
        # requests do, and keeps its transaction open for a moment so that the
        # others have to wait for its claim.
        instance = Topography.objects.get(pk=topo.pk)
        with transaction.atomic():
            claimed = run_task(instance)
            time.sleep(0.2)
        return claimed

    results = _in_threads(8, dispatch)

    assert results.count(True) == 1
    assert len(broker) == 1
    topo.refresh_from_db()
    assert topo.task_state == TaskStateModel.PENDING
    # The message carries the id the row was claimed with
    assert broker[0][1] == str(topo.task_id)


@pytest.mark.django_db(transaction=True)
def test_two_dispatches_in_quick_succession_process_once(broker):
    topo = _topography()
    broker.clear()

    first = Topography.objects.get(pk=topo.pk)
    second = Topography.objects.get(pk=topo.pk)
    assert run_task(first)
    assert not run_task(second)
    assert len(broker) == 1

    with mock.patch.object(
        Topography, "refresh_cache", autospec=True
    ) as refresh_cache:
        (_, task_id), = broker
        assert _deliver(topo, task_id) is True

    assert refresh_cache.call_count == 1
    topo.refresh_from_db()
    assert topo.task_state == TaskStateModel.SUCCESS


@pytest.mark.django_db(transaction=True)
def test_stale_instance_cannot_overwrite_the_claim(broker):
    topo = _topography()
    stale = Topography.objects.get(pk=topo.pk)
    assert run_task(topo)

    # The stale copy still believes the measurement is finished...
    assert stale.task_state == TaskStateModel.SUCCESS
    assert not run_task(stale)
    # ...but a failed claim reloads the task state, so saving it is harmless.
    assert stale.task_state == TaskStateModel.PENDING
    stale.save()
    stale.refresh_from_db()
    assert stale.task_state == TaskStateModel.PENDING
    assert stale.task_id == topo.task_id


@pytest.mark.django_db(transaction=True)
def test_claim_is_released_on_rollback(broker):
    topo = _topography()
    broker.clear()

    with pytest.raises(RuntimeError):
        with transaction.atomic():
            assert run_task(topo)
            raise RuntimeError("abort")

    assert broker == []
    topo.refresh_from_db()
    assert topo.task_state == TaskStateModel.SUCCESS


@pytest.mark.django_db
def test_unsaved_instance_cannot_be_dispatched():
    with pytest.raises(ValueError):
        run_task(Topography())


@pytest.mark.django_db(transaction=True)
def test_a_dispatch_the_broker_refused_is_failed():
    topo = _topography()

    with mock.patch.object(
        task_dispatch, "apply_async", side_effect=OSError("broker down")
    ):
        assert run_task(topo)

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.FAILURE
    assert "broker down" in stored.task_error
    assert topo.task_state == TaskStateModel.FAILURE
    # Nothing is left for a later save of the instance to undo
    topo.save()
    assert Topography.objects.get(pk=topo.pk).task_state == TaskStateModel.FAILURE


@pytest.mark.django_db(transaction=True)
def test_a_refused_dispatch_does_not_fail_a_newer_claim():
    topo = _topography()
    newer = []

    def refuse_after_a_newer_dispatch(args=None, kwargs=None, task_id=None, **options):
        if not newer:
            # A forced recompute claims the row before this message is refused
            other = Topography.objects.get(pk=topo.pk)
            with mock.patch.object(task_dispatch, "apply_async"):
                assert run_task(other, force=True)
            newer.append(other.task_id)
            raise OSError("broker down")

    with mock.patch.object(
        task_dispatch, "apply_async", side_effect=refuse_after_a_newer_dispatch
    ):
        assert run_task(topo)

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.PENDING
    assert stored.task_id == newer[0]


@pytest.mark.django_db(transaction=True)
def test_a_refused_dispatch_does_not_stop_the_others_in_its_transaction():
    first, second = _topography(), _topography()
    sent = []

    def refuse_the_first(args=None, kwargs=None, task_id=None, **options):
        if args[1] == first.pk:
            raise OSError("broker down")
        sent.append(args[1])

    with mock.patch.object(task_dispatch, "apply_async", side_effect=refuse_the_first):
        with transaction.atomic():
            assert run_task(first)
            assert run_task(second)

    assert sent == [second.pk]
    assert Topography.objects.get(pk=first.pk).task_state == TaskStateModel.FAILURE
    assert Topography.objects.get(pk=second.pk).task_state == TaskStateModel.PENDING


#
# Claim at the worker
#


@pytest.mark.django_db(transaction=True)
def test_duplicate_message_does_nothing(broker):
    topo = _topography()
    assert run_task(topo)
    task_id = topo.task_id

    with mock.patch.object(
        Topography, "refresh_cache", autospec=True
    ) as refresh_cache:
        assert _deliver(topo, task_id) is True
        # A second delivery of the same message, e.g. an SQS duplicate
        assert _deliver(topo, task_id) is None

    assert refresh_cache.call_count == 1
    topo.refresh_from_db()
    assert topo.task_state == TaskStateModel.SUCCESS


@pytest.mark.django_db(transaction=True)
def test_a_dropped_delivery_is_ignored_not_a_success(broker):
    """A dropped duplicate must not look like the live run finishing: no result
    is recorded for its id and no `task_success` is sent."""
    task_id = uuid.uuid4()
    topo = _topography(
        TaskStateModel.STARTED, task_id=task_id, task_start_time=timezone.now()
    )
    successes = []

    def record_success(sender=None, **kwargs):
        successes.append(sender)

    task_success.connect(record_success, weak=False)
    try:
        ct = ContentType.objects.get_for_model(Topography)
        result = task_dispatch.apply(args=[ct.id, topo.pk], task_id=str(task_id))
    finally:
        task_success.disconnect(record_success)

    assert result.state == celery.states.IGNORED
    assert successes == []
    topo.refresh_from_db()
    assert topo.task_state == TaskStateModel.STARTED


@pytest.mark.django_db(transaction=True)
def test_a_delivery_superseded_before_it_loads_the_row_does_not_run(broker):
    topo = _topography()
    assert run_task(topo)
    first = topo.task_id
    real_claim = utils.claim_started
    newer = []

    def claim_then_get_superseded(*args, **kwargs):
        started_at = real_claim(*args, **kwargs)
        if started_at is not None and not newer:
            # A forced recompute claims the row between the claim and the load
            assert run_task(Topography.objects.get(pk=topo.pk), force=True)
            newer.append(Topography.objects.get(pk=topo.pk).task_id)
        return started_at

    with mock.patch.object(utils, "claim_started", claim_then_get_superseded), \
            mock.patch.object(Topography, "refresh_cache", autospec=True) as refresh_cache:
        assert _deliver(topo, first) is None
        stored = Topography.objects.get(pk=topo.pk)
        # The newer claim stands...
        assert stored.task_state == TaskStateModel.PENDING
        assert stored.task_id == newer[0]
        # ...and its own delivery runs
        assert _deliver(topo, newer[0]) is True

    assert refresh_cache.call_count == 1
    assert Topography.objects.get(pk=topo.pk).task_state == TaskStateModel.SUCCESS


@pytest.mark.django_db(transaction=True)
def test_a_message_sent_before_its_row_names_it_waits_for_the_name(broker):
    """A dispatcher from before claims were introduced sends the message first
    and writes the task id afterwards."""
    task_id = uuid.uuid4()
    topo = _topography(TaskStateModel.PENDING, task_id=None)
    naps = []

    def dispatcher_catches_up(seconds):
        naps.append(seconds)
        Topography.objects.filter(pk=topo.pk).update(task_id=task_id)

    with mock.patch.object(utils.time, "sleep", dispatcher_catches_up), \
            mock.patch.object(Topography, "refresh_cache", autospec=True) as refresh_cache:
        assert _deliver(topo, task_id) is True

    assert naps == [utils.CLAIM_RETRY_DELAY]
    assert refresh_cache.call_count == 1
    assert Topography.objects.get(pk=topo.pk).task_state == TaskStateModel.SUCCESS


@pytest.mark.django_db(transaction=True)
def test_a_message_for_a_row_that_names_another_task_does_not_wait(broker):
    topo = _topography(TaskStateModel.PENDING, task_id=uuid.uuid4())

    with mock.patch.object(utils.time, "sleep") as sleep:
        assert _deliver(topo, uuid.uuid4()) is None

    sleep.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_a_message_for_a_deleted_row_does_not_wait(broker):
    topo = _topography(TaskStateModel.PENDING, task_id=None)
    task_id = uuid.uuid4()
    Topography.objects.filter(pk=topo.pk).delete()

    with mock.patch.object(utils.time, "sleep") as sleep:
        assert _deliver(topo, task_id) is None

    sleep.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_concurrent_deliveries_run_once(broker):
    topo = _topography()
    assert run_task(topo)
    task_id = topo.task_id
    calls = []

    def slow_refresh(self, timer=None):
        calls.append(self.pk)
        time.sleep(0.3)

    with mock.patch.object(Topography, "refresh_cache", slow_refresh):
        results = _in_threads(4, lambda i: _deliver(topo, task_id))

    assert calls == [topo.pk]
    assert sorted(results, key=str) == [None, None, None, True]


@pytest.mark.django_db(transaction=True)
def test_message_of_a_live_run_does_nothing(broker, settings):
    settings.TOPOBANK_TASK_RECLAIM_AFTER = 600
    task_id = uuid.uuid4()
    topo = _topography(
        TaskStateModel.STARTED,
        task_id=task_id,
        task_start_time=timezone.now() - timedelta(seconds=60),
    )

    with mock.patch.object(
        Topography, "refresh_cache", autospec=True
    ) as refresh_cache:
        assert _deliver(topo, task_id) is None

    refresh_cache.assert_not_called()
    topo.refresh_from_db()
    assert topo.task_state == TaskStateModel.STARTED


@pytest.mark.django_db(transaction=True)
def test_redelivery_after_a_dead_worker_reruns(broker, settings):
    settings.TOPOBANK_TASK_RECLAIM_AFTER = 600
    task_id = uuid.uuid4()
    topo = _topography(
        TaskStateModel.STARTED,
        task_id=task_id,
        task_start_time=timezone.now() - timedelta(seconds=1800),
    )

    with mock.patch.object(
        Topography, "refresh_cache", autospec=True
    ) as refresh_cache:
        assert _deliver(topo, task_id) is True

    assert refresh_cache.call_count == 1
    topo.refresh_from_db()
    assert topo.task_state == TaskStateModel.SUCCESS
    # The rerun recorded its own start
    assert topo.task_start_time > timezone.now() - timedelta(seconds=60)


@pytest.mark.django_db(transaction=True)
def test_without_a_configured_window_the_time_limit_decides(broker, settings):
    settings.TOPOBANK_TASK_RECLAIM_AFTER = None
    task_id = uuid.uuid4()
    topo = _topography(
        TaskStateModel.STARTED,
        task_id=task_id,
        task_start_time=timezone.now() - timedelta(seconds=1800),
    )

    with mock.patch.object(
        Topography, "refresh_cache", autospec=True
    ) as refresh_cache:
        # The run outlived the queue's visibility timeout, not its time limit:
        # the redelivery duplicates a live run
        with mock.patch.object(task_dispatch, "time_limit", 3600):
            assert _deliver(topo, task_id) is None
        refresh_cache.assert_not_called()
        # Past the time limit the worker has killed the run: the redelivery
        # reruns it
        with mock.patch.object(task_dispatch, "time_limit", 600):
            assert _deliver(topo, task_id) is True

    assert refresh_cache.call_count == 1
    topo.refresh_from_db()
    assert topo.task_state == TaskStateModel.SUCCESS


@pytest.mark.django_db(transaction=True)
def test_without_a_time_limit_a_started_run_is_never_taken_over(broker, settings):
    settings.TOPOBANK_TASK_RECLAIM_AFTER = None
    assert task_dispatch.app.conf.task_time_limit is None
    task_id = uuid.uuid4()
    topo = _topography(
        TaskStateModel.STARTED,
        task_id=task_id,
        task_start_time=timezone.now() - timedelta(days=30),
    )

    with mock.patch.object(task_dispatch, "time_limit", None), mock.patch.object(
        Topography, "refresh_cache", autospec=True
    ) as refresh_cache:
        assert _deliver(topo, task_id) is None

    refresh_cache.assert_not_called()
    topo.refresh_from_db()
    assert topo.task_state == TaskStateModel.STARTED


@pytest.mark.django_db(transaction=True)
def test_superseded_message_does_nothing(broker):
    topo = _topography()
    assert run_task(topo)
    old_task_id = topo.task_id
    assert run_task(topo, force=True)
    assert topo.task_id != old_task_id

    with mock.patch.object(
        Topography, "refresh_cache", autospec=True
    ) as refresh_cache:
        assert _deliver(topo, old_task_id) is None
        assert _deliver(topo, topo.task_id) is True

    assert refresh_cache.call_count == 1


@pytest.mark.django_db(transaction=True)
def test_message_for_a_row_never_marked_pending_still_runs(broker):
    # Messages queued before this change by callers that did not persist the
    # pending state: the row reads NOTRUN but carries the message's task id.
    task_id = uuid.uuid4()
    topo = _topography(TaskStateModel.NOTRUN, task_id=task_id)

    with mock.patch.object(
        Topography, "refresh_cache", autospec=True
    ) as refresh_cache:
        assert _deliver(topo, task_id) is True

    assert refresh_cache.call_count == 1


@pytest.mark.django_db
def test_claim_started_ignores_deleted_rows():
    assert not claim_started(Topography, 2**31 - 1, str(uuid.uuid4()))


#
# The end of a run
#


@pytest.mark.django_db(transaction=True)
def test_superseded_run_does_not_record_its_result(broker):
    topo = _topography()
    broker.clear()
    assert run_task(topo)
    task_id = topo.task_id

    def refresh_then_get_superseded(self, timer=None):
        # A forced recompute claims the measurement while this run is busy
        assert run_task(Topography.objects.get(pk=self.pk), force=True)

    with mock.patch.object(Topography, "refresh_cache", refresh_then_get_superseded):
        assert _deliver(topo, task_id) is True

    topo.refresh_from_db()
    # The successor's claim stands; this run's SUCCESS was not written over it
    assert topo.task_state == TaskStateModel.PENDING
    assert topo.task_id != task_id
    assert len(broker) == 2


@pytest.mark.django_db(transaction=True)
def test_end_of_run_only_writes_task_fields(broker):
    topo = _topography()
    assert run_task(topo)

    def edit_while_running(self, timer=None):
        Topography.objects.filter(pk=self.pk).update(description="edited meanwhile")

    with mock.patch.object(Topography, "refresh_cache", edit_while_running):
        assert _deliver(topo, topo.task_id) is True

    topo.refresh_from_db()
    assert topo.task_state == TaskStateModel.SUCCESS
    assert topo.description == "edited meanwhile"


@pytest.mark.django_db(transaction=True)
def test_the_end_of_a_run_overwrites_an_error_written_meanwhile(broker):
    topo = _topography()
    assert run_task(topo)

    def get_given_up_for_lost_while_running(self, timer=None):
        # A reaper took the run for lost, without taking the row from it
        Topography.objects.filter(pk=self.pk).update(
            task_state=TaskStateModel.FAILURE,
            task_error="assumed lost",
            task_traceback="Traceback: none",
        )

    with mock.patch.object(
        Topography, "refresh_cache", get_given_up_for_lost_while_running
    ):
        assert _deliver(topo, topo.task_id) is True

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.SUCCESS
    assert stored.task_error == ""
    assert stored.task_traceback is None


#
# Dispatch from a request
#


@pytest.mark.django_db(transaction=True)
def test_ensure_task_started_processes_an_unprocessed_measurement(broker):
    topo = _topography(TaskStateModel.NOTRUN)
    broker.clear()

    topo.ensure_task_started()

    assert len(broker) == 1
    assert Topography.objects.get(pk=topo.pk).task_state == TaskStateModel.PENDING


@pytest.mark.django_db(transaction=True)
def test_ensure_task_started_does_not_reprocess_a_finished_measurement(broker):
    topo = _topography(TaskStateModel.NOTRUN)
    broker.clear()
    # A request loaded the measurement, and a worker finished it in the meantime
    request_copy = Topography.objects.get(pk=topo.pk)
    Topography.objects.filter(pk=topo.pk).update(task_state=TaskStateModel.SUCCESS)

    request_copy.ensure_task_started()

    assert broker == []
    assert Topography.objects.get(pk=topo.pk).task_state == TaskStateModel.SUCCESS


#
# Saves of an instance that did not follow the task machinery
#


@pytest.mark.django_db(transaction=True)
def test_a_field_edited_in_place_is_still_saved(broker):
    topo = _topography()

    topo.instrument_parameters["tip_radius"] = {"value": 10, "unit": "nm"}
    topo.save()

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.instrument_parameters["tip_radius"] == {"value": 10, "unit": "nm"}


@pytest.mark.django_db(transaction=True)
def test_a_stale_full_save_does_not_undo_a_claim_or_a_start(broker):
    topo = _topography()
    # A request loaded the measurement before it was dispatched...
    stale = Topography.objects.get(pk=topo.pk)
    assert run_task(topo)
    assert claim_started(Topography, topo.pk, topo.task_id)
    started = Topography.objects.get(pk=topo.pk)

    # ...and saves it in full afterwards, e.g. a rename
    stale.name = "renamed"
    stale.save()

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.name == "renamed"
    assert stored.task_state == TaskStateModel.STARTED
    assert stored.task_id == started.task_id
    assert stored.task_start_time == started.task_start_time


@pytest.mark.django_db(transaction=True)
def test_a_worker_starting_inside_the_save_that_dispatched_it_keeps_its_start():
    """Outside a transaction the dispatching save() writes its row, claims and
    sends at once, so the worker can start before save() returns."""
    topo = _topography()

    def worker_starts_immediately(args=None, kwargs=None, task_id=None, **options):
        assert claim_started(Topography, args[1], task_id)

    with mock.patch.object(
        task_dispatch, "apply_async", side_effect=worker_starts_immediately
    ):
        topo.detrend_mode = "height"  # a significant field
        topo.save()

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.detrend_mode == "height"
    assert stored.task_state == TaskStateModel.STARTED
    assert stored.task_start_time is not None


@pytest.mark.django_db(transaction=True)
def test_a_significant_edit_during_a_run_supersedes_it(broker):
    topo = _topography()
    broker.clear()
    assert run_task(topo)
    first_run = topo.task_id
    seen_by_runs = []

    def refresh_while_the_user_edits(self, timer=None):
        seen_by_runs.append(self.detrend_mode)
        if len(seen_by_runs) == 1:
            user_copy = Topography.objects.get(pk=self.pk)
            user_copy.detrend_mode = "height"
            user_copy.save()

    with mock.patch.object(Topography, "refresh_cache", refresh_while_the_user_edits):
        assert _deliver(topo, first_run) is True
        stored = Topography.objects.get(pk=topo.pk)
        # The run that read the old setting recorded nothing...
        assert stored.task_state == TaskStateModel.PENDING
        assert stored.task_id != first_run
        # ...and a new one was dispatched, which reads the new setting
        assert len(broker) == 2
        assert _deliver(topo, stored.task_id) is True

    assert seen_by_runs == ["center", "height"]
    assert Topography.objects.get(pk=topo.pk).task_state == TaskStateModel.SUCCESS
