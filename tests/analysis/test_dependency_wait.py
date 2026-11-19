"""
A run whose chord fires while a shared dependency is pending or running again
(another parent's forced submit renewed it in place) waits for it instead of
failing with "Dependency 'x' failed." for a dependency that goes on to succeed.
"""

import datetime
from unittest.mock import patch

import pytest
from django.utils import timezone

from topobank.analysis import tasks
from topobank.analysis.models import (
    Workflow,
    WorkflowResult,
    submit_analysis_task_to_celery,
)
from topobank.analysis.tasks import (
    DEPENDENCY_WAIT_INTERVAL,
    DEPENDENCY_WAIT_LIMIT,
    execute_workflow,
)
from topobank.taskapp.celeryapp import app
from topobank.testing.factories import TopographyAnalysisFactory


@pytest.fixture
def worker_mode():
    """As on a worker: task_always_eager off, so countdowns are honoured. The
    tests patch apply_async, so nothing is published."""
    # The Django settings carry the namespaced key, which takes precedence.
    keys = ("CELERY_TASK_ALWAYS_EAGER", "task_always_eager")
    saved = {key: app.conf.get(key) for key in keys}
    app.conf.update({key: False for key in keys})
    try:
        assert not app.conf.task_always_eager
        yield
    finally:
        app.conf.update(saved)


def _analysis(topo, task_state=WorkflowResult.PENDING):
    wf = Workflow(name="topobank.testing.test")
    return TopographyAnalysisFactory.create(
        subject_topography=topo,
        workflow_name="topobank.testing.test",
        kwargs=wf.get_default_kwargs(),
        result=None,
        task_state=task_state,
    )


def _parent_of(topo, dep):
    parent = _analysis(topo, WorkflowResult.PENDING_DEPENDENCIES)
    parent.dependencies = {"features:0": dep.id}
    parent.save()
    return parent


def _delayed_run(parent, waited, task_id="4f1c0d2e-0000-0000-0000-00000000000a"):
    """A re-queued run as Celery delivers it: the row was claimed for its task
    id (execute_workflow does that before re-queueing), and the run arrives
    with that id."""
    WorkflowResult.objects.filter(pk=parent.pk).update(task_id=task_id)
    return execute_workflow.apply(
        args=(parent.id,), kwargs={"waited": waited}, task_id=task_id, throw=True
    )


@pytest.mark.django_db
@pytest.mark.parametrize("state", [WorkflowResult.PENDING, WorkflowResult.STARTED])
@pytest.mark.parametrize("via_apply", [False, True])
def test_waits_for_an_unfinished_dependency(
    two_topos, test_workflow, worker_mode, state, via_apply
):
    topo, _ = two_topos
    dep = _analysis(topo, state)
    parent = _parent_of(topo, dep)

    with patch.object(execute_workflow, "apply_async") as requeue:
        if via_apply:
            # schedule_workflow's shortcut: .apply() on a worker, so the request
            # is eager but the countdown of the re-queued task is honoured.
            execute_workflow.apply(args=(parent.id,), kwargs={"queue": "analysis"})
        else:
            execute_workflow(parent.id)

    requeue.assert_called_once()
    _, call = requeue.call_args
    assert call["countdown"] == DEPENDENCY_WAIT_INTERVAL
    assert call["kwargs"]["waited"] == DEPENDENCY_WAIT_INTERVAL
    if via_apply:
        assert call["queue"] == call["kwargs"]["queue"] == "analysis"
    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.PENDING_DEPENDENCIES
    assert str(parent.task_id) == str(call["task_id"])
    assert not parent.task_error


def _changing_parent_meanwhile(parent_id, **fields):
    """_read_dependencies, but the parent row changes right after the read, as
    when a dependency's worker fails it or a resubmission takes it over."""
    read = tasks._read_dependencies

    def read_then_change(analysis):
        deps = read(analysis)
        WorkflowResult.objects.filter(pk=parent_id).update(**fields)
        return deps

    return patch.object(tasks, "_read_dependencies", read_then_change)


@pytest.mark.django_db
def test_a_waiting_run_does_not_reopen_a_parent_failed_meanwhile(
    two_topos, test_workflow, worker_mode
):
    topo, _ = two_topos
    dep = _analysis(topo, WorkflowResult.PENDING)
    parent = _parent_of(topo, dep)

    with (
        _changing_parent_meanwhile(
            parent.id, task_state=WorkflowResult.FAILURE, task_error="dep failed"
        ),
        patch.object(execute_workflow, "apply_async") as requeue,
    ):
        execute_workflow(parent.id)

    requeue.assert_not_called()
    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.FAILURE
    assert parent.task_error == "dep failed"


@pytest.mark.django_db
def test_a_stale_run_leaves_a_resubmission_alone(
    two_topos, test_workflow, worker_mode
):
    topo, _ = two_topos
    dep = _analysis(topo, WorkflowResult.PENDING)
    parent = _parent_of(topo, dep)
    resubmission = "4f1c0d2e-0000-0000-0000-000000000002"

    with (
        _changing_parent_meanwhile(parent.id, task_id=resubmission),
        patch.object(execute_workflow, "apply_async") as requeue,
    ):
        execute_workflow(parent.id)

    requeue.assert_not_called()
    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.PENDING_DEPENDENCIES
    assert str(parent.task_id) == resubmission


@pytest.mark.django_db
def test_runs_once_the_dependency_has_succeeded(two_topos, test_workflow, worker_mode):
    topo, _ = two_topos
    dep = _analysis(topo, WorkflowResult.SUCCESS)
    parent = _parent_of(topo, dep)

    with patch.object(execute_workflow, "apply_async") as requeue:
        _delayed_run(parent, waited=DEPENDENCY_WAIT_INTERVAL)

    requeue.assert_not_called()
    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.SUCCESS


@pytest.mark.django_db
def test_gives_up_after_the_wait_limit_with_a_clear_message(
    two_topos, test_workflow, worker_mode
):
    topo, _ = two_topos
    dep = _analysis(topo, WorkflowResult.PENDING)
    parent = _parent_of(topo, dep)

    with (
        patch.object(execute_workflow, "apply_async") as requeue,
        pytest.raises(RuntimeError),
    ):
        _delayed_run(parent, waited=DEPENDENCY_WAIT_LIMIT)

    requeue.assert_not_called()
    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.FAILURE
    assert parent.task_error == (
        f"Dependency 'features:0' (topobank.testing.test #{dep.id}) was still "
        "pending when this workflow was due to start, probably because another "
        "run submitted it again. Submit this workflow again."
    )


@pytest.mark.django_db
def test_always_eager_fails_at_once_instead_of_recursing(two_topos, test_workflow):
    topo, _ = two_topos
    dep = _analysis(topo, WorkflowResult.STARTED)
    parent = _parent_of(topo, dep)

    execute_workflow.apply(args=(parent.id,))

    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.FAILURE
    assert "was still running when this workflow was due to start" in parent.task_error


@pytest.mark.django_db
def test_a_failed_dependency_without_an_error_is_named(two_topos, test_workflow):
    topo, _ = two_topos
    dep = _analysis(topo, WorkflowResult.FAILURE)
    parent = _parent_of(topo, dep)

    execute_workflow.apply(args=(parent.id,))

    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.FAILURE
    assert parent.task_error == (
        f"Dependency 'features:0' (topobank.testing.test #{dep.id}) failed "
        "without an error message."
    )


@pytest.mark.django_db
def test_a_failed_dependency_is_reported_even_if_another_is_unfinished(
    two_topos, test_workflow, worker_mode
):
    topo, _ = two_topos
    pending = _analysis(topo, WorkflowResult.PENDING)
    failed = _analysis(topo, WorkflowResult.FAILURE)
    failed.task_error = "Out of memory"
    failed.task_traceback = "Traceback: ..."
    failed.save()
    parent = _analysis(topo, WorkflowResult.PENDING_DEPENDENCIES)
    # The unfinished one first, so it would be found first.
    parent.dependencies = {"features:0": pending.id, "features:1": failed.id}
    parent.save()

    with (
        patch.object(execute_workflow, "apply_async") as requeue,
        pytest.raises(RuntimeError),
    ):
        execute_workflow(parent.id)

    requeue.assert_not_called()
    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.FAILURE
    assert parent.task_error == "Out of memory"
    assert parent.task_traceback == "Traceback: ..."


@pytest.mark.django_db
def test_a_delayed_run_superseded_by_a_resubmission_does_nothing(
    two_topos, test_workflow, worker_mode
):
    """An old waiter arriving after the workflow was submitted again must
    neither act for the new run nor fail it with its own wait budget."""
    topo, _ = two_topos
    dep = _analysis(topo, WorkflowResult.PENDING)
    parent = _parent_of(topo, dep)
    old, resubmission = (
        "4f1c0d2e-0000-0000-0000-0000000000b1",
        "4f1c0d2e-0000-0000-0000-0000000000b2",
    )
    # The row was claimed for the old waiter, then a resubmission took it over
    WorkflowResult.objects.filter(pk=parent.pk).update(task_id=resubmission)

    with patch.object(execute_workflow, "apply_async") as requeue:
        execute_workflow.apply(
            args=(parent.id,),
            kwargs={"waited": DEPENDENCY_WAIT_LIMIT},
            task_id=old,
            throw=True,
        )

    requeue.assert_not_called()
    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.PENDING_DEPENDENCIES
    assert str(parent.task_id) == resubmission


@pytest.mark.django_db
def test_a_failed_requeue_does_not_leave_the_workflow_waiting(
    two_topos, test_workflow, worker_mode
):
    """If publishing the re-queued task fails, the row must not keep pointing to
    a task that never runs: the lost-task sweep skips waiting rows."""
    topo, _ = two_topos
    dep = _analysis(topo, WorkflowResult.PENDING)
    parent = _parent_of(topo, dep)

    with (
        patch.object(
            execute_workflow, "apply_async", side_effect=ConnectionError("broker down")
        ),
        pytest.raises(ConnectionError),
    ):
        execute_workflow(parent.id)

    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.FAILURE
    assert "could not be queued again" in parent.task_error
    assert "broker down" in parent.task_error


@pytest.mark.django_db
def test_a_stale_run_does_not_start_over_a_resubmission(
    two_topos, test_workflow, worker_mode
):
    """The dependencies have succeeded, but a resubmission takes the row over
    while they are read: the stale run must not mark it STARTED with its own
    task id, nor compute."""
    topo, _ = two_topos
    dep = _analysis(topo, WorkflowResult.SUCCESS)
    parent = _parent_of(topo, dep)
    resubmission = "4f1c0d2e-0000-0000-0000-000000000003"

    with (
        _changing_parent_meanwhile(
            parent.id, task_state=WorkflowResult.PENDING, task_id=resubmission
        ),
        patch.object(WorkflowResult, "eval_self") as compute,
    ):
        execute_workflow(parent.id)

    compute.assert_not_called()
    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.PENDING
    assert str(parent.task_id) == resubmission


@pytest.mark.django_db
def test_the_chord_id_does_not_overwrite_a_requeue_of_its_callback(
    two_topos, test_workflow, worker_mode
):
    """The chord callback can run, and re-queue itself, before schedule_workflow
    stores the chord's id: that id must not replace the re-queued task's, whose
    ownership check would then fail and leave the workflow waiting for good."""
    topo, _ = two_topos
    dep = _analysis(topo, WorkflowResult.PENDING)
    parent = _analysis(topo, WorkflowResult.PENDING)
    requeued = "4f1c0d2e-0000-0000-0000-000000000004"
    chord_id = "4f1c0d2e-0000-0000-0000-000000000005"

    def callback_runs_first(*args, **kwargs):
        # What the callback does when it finds the dependency still unfinished.
        WorkflowResult.objects.filter(pk=parent.pk).update(task_id=requeued)
        return type("Result", (), {"id": chord_id})()

    chord = patch.object(tasks.celery, "chord")
    with (
        patch.object(Workflow, "get_dependencies", return_value={"features:0": dep}),
        patch.object(
            tasks, "prepare_dependency_tasks", return_value=({}, {"features:0": dep})
        ),
        chord as make_chord,
    ):
        make_chord.return_value.apply_async.side_effect = callback_runs_first
        tasks.schedule_workflow.apply(args=(parent.id, False), throw=True)

    make_chord.return_value.apply_async.assert_called_once()
    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.PENDING_DEPENDENCIES
    assert str(parent.task_id) == requeued


@pytest.mark.django_db
def test_the_row_names_the_chord_callback_before_the_chord_is_published(
    two_topos, test_workflow, worker_mode
):
    """The callback can run before `schedule_workflow` gets past publishing the
    chord; it must find its own id on the row then, not the scheduler's."""
    topo, _ = two_topos
    dep = _analysis(topo, WorkflowResult.PENDING)
    parent = _analysis(topo, WorkflowResult.PENDING)
    seen_at_publication = []

    def publish(*args, **kwargs):
        seen_at_publication.append(
            str(WorkflowResult.objects.get(pk=parent.pk).task_id)
        )

    with (
        patch.object(Workflow, "get_dependencies", return_value={"features:0": dep}),
        patch.object(
            tasks, "prepare_dependency_tasks", return_value=({}, {"features:0": dep})
        ),
        patch.object(tasks.celery, "chord") as make_chord,
    ):
        make_chord.return_value.apply_async.side_effect = publish
        tasks.schedule_workflow.apply(args=(parent.id, False), throw=True)

    callback = make_chord.call_args.args[1]
    callback_id = str(callback.options["task_id"])
    assert seen_at_publication == [callback_id]
    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.PENDING_DEPENDENCIES
    assert str(parent.task_id) == callback_id


@pytest.mark.django_db
def test_a_chord_that_cannot_be_published_fails_the_workflow(
    two_topos, test_workflow, worker_mode
):
    topo, _ = two_topos
    dep = _analysis(topo, WorkflowResult.PENDING)
    parent = _analysis(topo, WorkflowResult.PENDING)

    with (
        patch.object(Workflow, "get_dependencies", return_value={"features:0": dep}),
        patch.object(
            tasks, "prepare_dependency_tasks", return_value=({}, {"features:0": dep})
        ),
        patch.object(tasks.celery, "chord") as make_chord,
    ):
        make_chord.return_value.apply_async.side_effect = OSError("broker down")
        with pytest.raises(OSError):
            tasks.schedule_workflow.apply(args=(parent.id, False), throw=True)

    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.FAILURE
    assert "could not be queued" in parent.task_error


@pytest.mark.django_db
def test_the_submission_names_its_task_before_publishing_it(
    two_topos, test_workflow
):
    """`schedule_workflow` can run, and hand the row on to a chord callback or a
    re-queued run, before the submission returns: the submission must not
    overwrite that with its own id afterwards."""
    topo, _ = two_topos
    analysis = _analysis(topo, WorkflowResult.PENDING)
    analysis.set_pending_state()
    handed_on = "4f1c0d2e-0000-0000-0000-000000000007"
    seen_at_publication = []

    def runs_at_once(args=None, queue=None, task_id=None, **kwargs):
        seen_at_publication.append(
            (str(WorkflowResult.objects.get(pk=analysis.pk).task_id), task_id)
        )
        WorkflowResult.objects.filter(pk=analysis.pk).update(
            task_state=WorkflowResult.PENDING_DEPENDENCIES, task_id=handed_on
        )

    with patch.object(tasks.schedule_workflow, "apply_async", side_effect=runs_at_once):
        submit_analysis_task_to_celery(analysis, True)

    ((on_row, published),) = seen_at_publication
    assert on_row == published
    analysis.refresh_from_db()
    assert str(analysis.task_id) == handed_on


@pytest.mark.django_db
def test_a_submission_that_cannot_be_published_fails_the_workflow(
    two_topos, test_workflow
):
    topo, _ = two_topos
    analysis = _analysis(topo, WorkflowResult.PENDING)
    analysis.set_pending_state()

    with patch.object(
        tasks.schedule_workflow, "apply_async", side_effect=OSError("broker down")
    ):
        with pytest.raises(OSError):
            submit_analysis_task_to_celery(analysis, True)

    analysis.refresh_from_db()
    assert analysis.task_state == WorkflowResult.FAILURE
    assert "could not be queued" in analysis.task_error


@pytest.mark.django_db
def test_a_poll_lost_before_it_was_published_is_failed_past_its_deadline(
    two_topos, test_workflow, worker_mode
):
    """The worker dies between claiming the row for the next poll and
    publishing it: the deadline persisted with the claim lets the custodian
    fail the row, which nothing else would ever move."""
    from topobank.analysis.custodian import fail_abandoned_waiters

    topo, _ = two_topos
    dep = _analysis(topo, WorkflowResult.STARTED)
    parent = _parent_of(topo, dep)

    with patch.object(execute_workflow, "apply_async", side_effect=SystemExit()):
        with pytest.raises(SystemExit):
            execute_workflow(parent.id)

    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.PENDING_DEPENDENCIES
    deadline = parent.task_wait_deadline
    assert deadline is not None

    assert fail_abandoned_waiters(now=deadline) == 0
    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.PENDING_DEPENDENCIES

    assert fail_abandoned_waiters(now=deadline + datetime.timedelta(seconds=1)) == 1
    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.FAILURE
    assert "stopped waiting" in parent.task_error


@pytest.mark.django_db
def test_each_poll_pushes_the_deadline_on(two_topos, test_workflow, worker_mode):
    topo, _ = two_topos
    dep = _analysis(topo, WorkflowResult.STARTED)
    parent = _parent_of(topo, dep)

    with patch.object(execute_workflow, "apply_async"):
        execute_workflow(parent.id)
        parent.refresh_from_db()
        first = parent.task_wait_deadline
        _delayed_run(
            parent, waited=DEPENDENCY_WAIT_INTERVAL, task_id=str(parent.task_id)
        )

    parent.refresh_from_db()
    assert parent.task_wait_deadline > first


@pytest.mark.django_db
def test_a_workflow_waiting_for_its_chord_has_no_deadline(two_topos, test_workflow):
    from topobank.analysis.custodian import fail_abandoned_waiters

    topo, _ = two_topos
    dep = _analysis(topo, WorkflowResult.PENDING)
    parent = _analysis(topo, WorkflowResult.PENDING)
    with (
        patch.object(Workflow, "get_dependencies", return_value={"features:0": dep}),
        patch.object(
            tasks, "prepare_dependency_tasks", return_value=({}, {"features:0": dep})
        ),
        patch.object(tasks.celery, "chord"),
    ):
        tasks.schedule_workflow.apply(args=(parent.id, False), throw=True)

    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.PENDING_DEPENDENCIES
    assert parent.task_wait_deadline is None
    far_future = timezone.now() + datetime.timedelta(days=365)
    assert fail_abandoned_waiters(now=far_future) == 0


@pytest.mark.django_db
def test_lost_waiters_are_judged_only_while_workers_answer(
    two_topos, test_workflow
):
    """With no worker up no poll runs, and every deadline passes."""
    from topobank.taskapp import custodian

    topo, _ = two_topos
    dep = _analysis(topo, WorkflowResult.STARTED)
    parent = _parent_of(topo, dep)
    WorkflowResult.objects.filter(pk=parent.pk).update(
        task_wait_deadline=timezone.now() - datetime.timedelta(minutes=1)
    )

    with patch.object(custodian, "live_task_ids", return_value=None):
        custodian.reap_lost_tasks(require_confirmation=False)
    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.PENDING_DEPENDENCIES

    with patch.object(custodian, "live_task_ids", return_value=set()):
        custodian.reap_lost_tasks(require_confirmation=False)
    parent.refresh_from_db()
    assert parent.task_state == WorkflowResult.FAILURE
