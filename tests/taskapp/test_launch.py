"""
Tests for the launch API (``topobank.taskapp.launch``) and the status contract
(``topobank.taskapp.status``).

The point of the launch API is that topobank hands work to *a* workflow manager
without knowing how it runs. These tests prove that by swapping in a fake
manager that records what it was asked to do, and by driving the status
contract directly, the way any manager would.
"""

import uuid

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

# Registers the "topobank.testing.test" workflow implementation
import topobank.testing.workflows  # noqa: E402,F401
from topobank.analysis.models import WorkflowResult
from topobank.manager.models import Topography
from topobank.taskapp.celery_manager import CeleryWorkflowManager
from topobank.taskapp.launch import (
    LaunchHandle,
    LaunchRequest,
    RunInfo,
    WorkflowManager,
    get_workflow_manager,
    launch,
)
from topobank.taskapp.models import TaskStateModel
from topobank.taskapp.status import FileEntry, StatusReport, apply_status_report
from topobank.taskapp.utils import run_task
from topobank.testing.factories import Topography1DFactory, TopographyAnalysisFactory


class FakeWorkflowManager:
    """A manager that runs nothing and remembers everything."""

    name = "fake"
    launched = []
    cancelled = []
    state = TaskStateModel.STARTED

    def launch(self, request, instance=None):
        type(self).launched.append(request)
        return LaunchHandle(manager=self.name, data={"run": str(uuid.uuid4())})

    def poll(self, handle, instance=None):
        return RunInfo(state=type(self).state, progress=42.0, messages=["working"])

    def cancel(self, handle, instance=None):
        type(self).cancelled.append(handle)


FAKE = {"fake": f"{FakeWorkflowManager.__module__}.FakeWorkflowManager"}


@pytest.fixture(autouse=True)
def _reset_fake():
    FakeWorkflowManager.launched = []
    FakeWorkflowManager.cancelled = []
    FakeWorkflowManager.state = TaskStateModel.STARTED


def _analysis(test_workflow, **overrides):
    params = dict(workflow_name=test_workflow.name, kwargs=dict(a=1, b="x"), result=None)
    params.update(overrides)
    return TopographyAnalysisFactory.create(**params)


# ---------------------------------------------------------------------------
# Manager resolution
# ---------------------------------------------------------------------------


def test_default_manager_is_celery():
    manager = get_workflow_manager()
    assert isinstance(manager, CeleryWorkflowManager)
    assert isinstance(manager, WorkflowManager)


@override_settings(TOPOBANK_WORKFLOW_MANAGERS=FAKE, TOPOBANK_WORKFLOW_MANAGER="fake")
def test_manager_is_settings_driven():
    assert isinstance(get_workflow_manager(), FakeWorkflowManager)
    # The built-in Celery manager stays reachable by name
    assert isinstance(get_workflow_manager("celery"), CeleryWorkflowManager)


def test_unknown_manager_is_a_configuration_error():
    with pytest.raises(ImproperlyConfigured):
        get_workflow_manager("no-such-manager")


# ---------------------------------------------------------------------------
# Envelope and handle
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_workflow_result_builds_workflow_envelope(test_workflow):
    a = _analysis(test_workflow, metadata={"parent_workflow_result_id": 17})
    request = a.build_launch_request(force=True)
    assert request.kind == "workflow"
    assert request.model == "analysis.workflowresult"
    assert request.pk == a.pk
    assert request.force is True
    assert request.workflow_name == test_workflow.name
    assert request.kwargs == dict(a=1, b="x")
    assert request.subject_hash == a.subject_hash
    assert request.storage_prefix == a.storage_prefix
    assert request.user_id == a.created_by_id
    assert request.parent_id == 17
    assert request.queue == a.get_queue()
    # The envelope is serialisable: a manager may ship it anywhere
    LaunchRequest.model_validate_json(request.model_dump_json())


@pytest.mark.django_db
def test_topography_builds_task_envelope():
    topo = Topography1DFactory()
    request = topo.build_launch_request(args=[1], task_kwargs={"k": 2})
    assert request.kind == "task"
    assert request.model == "manager.topography"
    assert request.queue == topo.celery_queue
    assert request.args == [1]
    assert request.task_kwargs == {"k": 2}


def test_handle_roundtrips_through_json():
    handle = LaunchHandle(manager="celery", data={"task_id": "abc", "pk": 3})
    assert LaunchHandle(**handle.model_dump()) == handle


@pytest.mark.django_db
def test_launch_handle_falls_back_to_default_manager(test_workflow):
    a = _analysis(test_workflow, execution_handle=None)
    handle = a.get_launch_handle()
    assert handle.manager == "celery"
    assert handle.data == {"model": "analysis.workflowresult", "pk": a.pk}


# ---------------------------------------------------------------------------
# Launching, polling and cancelling through a swapped-in manager
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(TOPOBANK_WORKFLOW_MANAGERS=FAKE, TOPOBANK_WORKFLOW_MANAGER="fake")
def test_launch_stores_handle_and_hands_envelope_to_manager(test_workflow):
    a = _analysis(test_workflow)
    handle = launch(a, force=True)
    a.refresh_from_db()
    assert a.execution_handle == handle.model_dump()
    assert a.execution_handle["manager"] == "fake"
    [request] = FakeWorkflowManager.launched
    assert request.pk == a.pk and request.kind == "workflow" and request.force


@pytest.mark.django_db(transaction=True)
@override_settings(TOPOBANK_WORKFLOW_MANAGERS=FAKE, TOPOBANK_WORKFLOW_MANAGER="fake")
def test_submit_goes_through_the_launch_api(test_workflow):
    topo = Topography1DFactory()
    analysis = test_workflow.submit(topo.created_by, topo, dict(a=1, b="2"))
    analysis.refresh_from_db()
    assert analysis.execution_handle["manager"] == "fake"
    # The topography factory also refreshes its cache through the launch API
    # (a "task" request); only the workflow launch is of interest here.
    workflows = [r for r in FakeWorkflowManager.launched if r.kind == "workflow"]
    assert [r.pk for r in workflows] == [analysis.pk]


@pytest.mark.django_db(transaction=True)
@override_settings(TOPOBANK_WORKFLOW_MANAGERS=FAKE, TOPOBANK_WORKFLOW_MANAGER="fake")
def test_run_task_goes_through_the_launch_api():
    topo = Topography1DFactory()
    Topography.objects.filter(pk=topo.pk).update(task_state=TaskStateModel.NOTRUN)
    topo.refresh_from_db()
    FakeWorkflowManager.launched = []
    run_task(topo, force=True)
    topo.save()
    [request] = FakeWorkflowManager.launched
    assert request.kind == "task"
    assert request.model == "manager.topography"
    assert request.pk == topo.pk
    topo.refresh_from_db()
    assert topo.execution_handle["manager"] == "fake"


@pytest.mark.django_db
@override_settings(TOPOBANK_WORKFLOW_MANAGERS=FAKE)
def test_state_progress_and_cancel_route_to_the_manager_of_the_handle(test_workflow):
    # The row was launched by the fake manager; the default manager is still
    # Celery. Polling must go to the manager named in the handle.
    a = _analysis(
        test_workflow,
        task_state=TaskStateModel.STARTED,
        execution_handle={"manager": "fake", "data": {}},
    )
    assert a.get_celery_state() == TaskStateModel.STARTED
    assert a.get_task_state() == TaskStateModel.STARTED
    assert a.get_task_progress() == 42.0
    assert a.get_task_messages() == ["working"]
    a.cancel_task()
    assert len(FakeWorkflowManager.cancelled) == 1


@pytest.mark.django_db
@override_settings(TOPOBANK_WORKFLOW_MANAGERS=FAKE)
def test_manager_failure_overrides_self_reported_state(test_workflow):
    a = _analysis(
        test_workflow,
        task_state=TaskStateModel.STARTED,
        execution_handle={"manager": "fake", "data": {}},
    )
    FakeWorkflowManager.state = TaskStateModel.FAILURE
    assert a.get_task_state() == TaskStateModel.FAILURE


@pytest.mark.django_db
def test_set_pending_state_clears_handle(test_workflow):
    a = _analysis(test_workflow, execution_handle={"manager": "fake", "data": {}})
    a.set_pending_state()
    a.refresh_from_db()
    assert a.execution_handle is None


# ---------------------------------------------------------------------------
# Status contract
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_started_report_sets_start_time(test_workflow):
    a = _analysis(
        test_workflow,
        task_state=TaskStateModel.PENDING,
        task_start_time=None,
        task_end_time=None,
    )
    assert apply_status_report(a, StatusReport(state=TaskStateModel.STARTED))
    a.refresh_from_db()
    assert a.task_state == TaskStateModel.STARTED
    assert a.task_start_time is not None
    assert a.task_end_time is None


@pytest.mark.django_db
def test_claim_is_won_exactly_once(test_workflow):
    a = _analysis(test_workflow, task_state=TaskStateModel.PENDING)
    b = WorkflowResult.objects.get(pk=a.pk)  # a second worker's view of the row
    assert apply_status_report(a, StatusReport(state=TaskStateModel.STARTED), claim=True)
    assert not apply_status_report(b, StatusReport(state=TaskStateModel.STARTED), claim=True)
    # The loser sees the winner's state, not its own optimistic one
    assert b.task_state == TaskStateModel.STARTED


@pytest.mark.django_db
def test_claim_is_refused_on_a_finished_row(test_workflow):
    a = _analysis(test_workflow, task_state=TaskStateModel.SUCCESS)
    assert not apply_status_report(a, StatusReport(state=TaskStateModel.STARTED), claim=True)
    a.refresh_from_db()
    assert a.task_state == TaskStateModel.SUCCESS


@pytest.mark.django_db
def test_success_report_records_outcome(test_workflow):
    a = _analysis(test_workflow, task_state=TaskStateModel.STARTED)
    apply_status_report(
        a,
        StatusReport(
            state=TaskStateModel.SUCCESS,
            memory=12345,
            timer={"timers": {"x": 1.0}},
            dois=["10.1000/xyz"],
        ),
    )
    a.refresh_from_db()
    assert a.task_state == TaskStateModel.SUCCESS
    assert a.task_end_time is not None
    assert a.task_memory == 12345
    assert a.task_timer == {"timers": {"x": 1.0}}
    assert a.dois == ["10.1000/xyz"]


@pytest.mark.django_db
def test_failure_report_records_error_and_strips_nul(test_workflow):
    a = _analysis(test_workflow, task_state=TaskStateModel.STARTED)
    apply_status_report(
        a,
        StatusReport(state=TaskStateModel.FAILURE, error="boom\x00", traceback="tb\x00"),
    )
    a.refresh_from_db()
    assert a.task_state == TaskStateModel.FAILURE
    assert a.task_error == "boom"
    assert a.task_traceback == "tb"
    assert a.task_end_time is not None


@pytest.mark.django_db
def test_files_in_a_success_report_become_manifests(test_workflow):
    a = _analysis(test_workflow, task_state=TaskStateModel.STARTED)
    files = [
        FileEntry(
            filename="model.nc",
            path=f"{a.storage_prefix}/model.nc",
            size_bytes=10,
            content_type="application/x-netcdf",
        ),
        FileEntry(filename="result.json", path=f"{a.storage_prefix}/result.json"),
    ]
    apply_status_report(a, StatusReport(state=TaskStateModel.SUCCESS, files=files))
    names = {m.filename: m for m in a.folder.get_valid_files()}
    assert set(names) >= {"model.nc", "result.json"}
    assert names["model.nc"].file.name == f"{a.storage_prefix}/model.nc"
    assert names["model.nc"].size_bytes == 10
    assert names["model.nc"].content_type == "application/x-netcdf"
    assert names["model.nc"].kind == "der"
    assert names["model.nc"].permissions == a.folder.permissions
    # Registering again is idempotent
    apply_status_report(a, StatusReport(state=TaskStateModel.SUCCESS, files=files))
    assert a.folder.files.filter(filename="model.nc").count() == 1


_HOOK_CALLS = []


def _hook(instance, report):
    _HOOK_CALLS.append((instance.pk, report.state))


@pytest.mark.django_db
@override_settings(TOPOBANK_TASK_LIFECYCLE_HOOKS=[f"{__name__}._hook"])
def test_lifecycle_hooks_fire_on_every_report(test_workflow):
    _HOOK_CALLS.clear()
    a = _analysis(test_workflow, task_state=TaskStateModel.PENDING)
    apply_status_report(a, StatusReport(state=TaskStateModel.STARTED))
    apply_status_report(a, StatusReport(state=TaskStateModel.SUCCESS))
    assert _HOOK_CALLS == [(a.pk, TaskStateModel.STARTED), (a.pk, TaskStateModel.SUCCESS)]


@pytest.mark.django_db
@override_settings(TOPOBANK_TASK_LIFECYCLE_HOOKS=["os.path.no_such_hook"])
def test_failing_hook_does_not_block_the_report(test_workflow):
    a = _analysis(test_workflow, task_state=TaskStateModel.PENDING)
    apply_status_report(a, StatusReport(state=TaskStateModel.SUCCESS))
    a.refresh_from_db()
    assert a.task_state == TaskStateModel.SUCCESS


# ---------------------------------------------------------------------------
# Celery manager specifics
# ---------------------------------------------------------------------------


@override_settings(CELERY_LOGICAL_QUEUE_MAP={"analysis": "prod-analysis"})
def test_celery_manager_maps_logical_queues():
    manager = CeleryWorkflowManager()
    assert manager.resolve_queue("analysis") == "prod-analysis"
    assert manager.resolve_queue("manager") == "manager"
    assert manager.resolve_queue(None) is None


@pytest.mark.django_db
def test_get_celery_queue_is_the_mapped_logical_queue(test_workflow):
    a = _analysis(test_workflow)
    with override_settings(CELERY_LOGICAL_QUEUE_MAP={a.get_queue(): "mapped"}):
        assert a.get_celery_queue() == "mapped"
