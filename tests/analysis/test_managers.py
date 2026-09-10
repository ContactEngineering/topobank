"""
Tests for workflow managers (``topobank.analysis.managers``), per-manager
registries, and the status contract (``topobank.analysis.status``).

The point of the manager interface is that topobank hands a `WorkflowResult`
to *a* workflow manager without knowing how it runs. These tests prove that by
configuring a fake manager with its own registry and a fake workflow, and by
driving the status contract directly, the way any manager would.
"""

import uuid

import pydantic
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

# Registers the "topobank.testing.test" workflow with the Celery manager
import topobank.testing.workflows  # noqa: E402,F401
from topobank.analysis.celery_manager import CeleryWorkflowManager
from topobank.analysis.celery_manager import registry as celery_registry
from topobank.analysis.descriptor import WorkflowDescriptor
from topobank.analysis.managers import (
    LaunchHandle,
    RunInfo,
    WorkflowManager,
    WorkflowRegistry,
    get_workflow_manager,
    get_workflow_managers,
    get_workflow_names,
    manager_for_result,
    resolve_workflow,
)
from topobank.analysis.models import Workflow, WorkflowResult, submit_workflow
from topobank.analysis.registry import get_implementation
from topobank.analysis.status import FileEntry, StatusReport, apply_status_report
from topobank.manager.models import Topography
from topobank.testing.factories import Topography1DFactory, TopographyAnalysisFactory

FAKE_WORKFLOW = "tests.fake.workflow"


class FakeWorkflow(WorkflowDescriptor):
    """A workflow only the fake manager can run."""

    class Meta:
        name = FAKE_WORKFLOW
        display_name = "Fake workflow"
        subject_types = (Topography,)

    class Parameters(pydantic.BaseModel):
        model_config = pydantic.ConfigDict(extra="forbid")
        n: int = 3


class FakeWorkflowManager:
    """A manager that runs nothing and remembers everything."""

    name = "fake"
    registry = WorkflowRegistry()
    launched = []
    cancelled = []
    state = WorkflowResult.STARTED

    def launch(self, result, *, force=False):
        type(self).launched.append((result.pk, force))
        return LaunchHandle(manager=self.name, data={"run": str(uuid.uuid4())})

    def poll(self, result):
        return RunInfo(state=type(self).state, progress=42.0, messages=["working"])

    def cancel(self, result):
        type(self).cancelled.append(result.pk)


FakeWorkflowManager.registry.register(FakeWorkflow)

FAKE_PATH = f"{FakeWorkflowManager.__module__}.FakeWorkflowManager"
CELERY_PATH = f"{CeleryWorkflowManager.__module__}.CeleryWorkflowManager"


@pytest.fixture(autouse=True)
def _reset_fake():
    FakeWorkflowManager.launched = []
    FakeWorkflowManager.cancelled = []
    FakeWorkflowManager.state = WorkflowResult.STARTED


def _analysis(test_workflow, **overrides):
    params = dict(workflow_name=test_workflow.name, kwargs=dict(a=1, b="x"), result=None)
    params.update(overrides)
    return TopographyAnalysisFactory.create(**params)


# ---------------------------------------------------------------------------
# Managers and registries
# ---------------------------------------------------------------------------


def test_celery_manager_is_always_available():
    managers = get_workflow_managers()
    assert [m.name for m in managers] == ["celery"]
    assert isinstance(managers[0], CeleryWorkflowManager)
    assert isinstance(managers[0], WorkflowManager)
    # Singleton: the same instance is handed out again
    assert get_workflow_manager("celery") is managers[0]


@override_settings(TOPOBANK_WORKFLOW_MANAGERS=[FAKE_PATH])
def test_managers_come_from_settings_in_priority_order():
    assert [m.name for m in get_workflow_managers()] == ["fake", "celery"]


def test_unknown_manager_is_a_configuration_error():
    with pytest.raises(ImproperlyConfigured):
        get_workflow_manager("no-such-manager")


def test_registry_requires_name_and_display_name():
    registry = WorkflowRegistry()

    class Nameless(WorkflowDescriptor):
        class Meta:
            display_name = "x"

    with pytest.raises(ImproperlyConfigured):
        registry.register(Nameless)


def test_register_implementation_targets_the_celery_registry(test_workflow):
    # The testing workflow was registered through the historical entry point
    assert celery_registry.get(test_workflow.name) is not None
    assert get_implementation(name=test_workflow.name) is celery_registry.get(test_workflow.name)


# ---------------------------------------------------------------------------
# Resolution by name
# ---------------------------------------------------------------------------


def test_workflow_resolves_to_its_manager(test_workflow):
    manager, descriptor = resolve_workflow(test_workflow.name)
    assert manager.name == "celery"
    assert descriptor.Meta.name == test_workflow.name
    assert resolve_workflow("no.such.workflow") is None


@override_settings(TOPOBANK_WORKFLOW_MANAGERS=[FAKE_PATH])
def test_names_are_the_union_over_managers(test_workflow):
    names = get_workflow_names()
    assert FAKE_WORKFLOW in names
    assert test_workflow.name in names
    manager, descriptor = resolve_workflow(FAKE_WORKFLOW)
    assert manager.name == "fake"
    assert descriptor is FakeWorkflow


def test_fake_workflow_is_unknown_without_its_manager():
    assert resolve_workflow(FAKE_WORKFLOW) is None
    assert FAKE_WORKFLOW not in get_workflow_names()


@override_settings(TOPOBANK_WORKFLOW_MANAGERS=[FAKE_PATH])
def test_first_manager_wins_on_a_shared_name(test_workflow):
    # The fake manager claims a workflow the Celery manager also provides
    class Shadow(WorkflowDescriptor):
        class Meta:
            name = test_workflow.name
            display_name = "Shadow"

    FakeWorkflowManager.registry.register(Shadow)
    try:
        manager, descriptor = resolve_workflow(test_workflow.name)
        assert manager.name == "fake" and descriptor is Shadow
        assert get_workflow_names().count(test_workflow.name) == 1
    finally:
        FakeWorkflowManager.registry.unregister(test_workflow.name)
    manager, _ = resolve_workflow(test_workflow.name)
    assert manager.name == "celery"


@override_settings(TOPOBANK_WORKFLOW_MANAGERS=[FAKE_PATH])
def test_workflow_value_object_uses_the_descriptor():
    wf = Workflow(FAKE_WORKFLOW)
    assert wf.display_name == "Fake workflow"
    assert wf.has_implementation(Topography)
    assert wf.get_default_kwargs() == {"n": 3}
    assert wf.clean_kwargs({"n": 5}) == {"n": 5}
    assert "n" in wf.get_kwargs_schema()["properties"]
    with pytest.raises(pydantic.ValidationError):
        wf.clean_kwargs({"m": 1})


# ---------------------------------------------------------------------------
# Launching, polling and cancelling through the manager of a result
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(TOPOBANK_WORKFLOW_MANAGERS=[FAKE_PATH])
def test_submit_workflow_launches_on_the_resolved_manager():
    topo = Topography1DFactory()
    a = TopographyAnalysisFactory.create(
        subject_topography=topo, workflow_name=FAKE_WORKFLOW, kwargs={"n": 1}, result=None
    )
    submit_workflow(a, True)
    a.refresh_from_db()
    assert a.execution_handle["manager"] == "fake"
    assert FakeWorkflowManager.launched == [(a.pk, True)]
    assert manager_for_result(a).name == "fake"


@pytest.mark.django_db(transaction=True)
@override_settings(TOPOBANK_WORKFLOW_MANAGERS=[FAKE_PATH])
def test_workflow_submit_goes_through_the_manager():
    topo = Topography1DFactory()
    analysis = Workflow(FAKE_WORKFLOW).submit(topo.created_by, topo, {"n": 2})
    analysis.refresh_from_db()
    assert analysis.execution_handle["manager"] == "fake"
    assert [pk for pk, _ in FakeWorkflowManager.launched] == [analysis.pk]


@pytest.mark.django_db
def test_unknown_workflow_fails_the_result_instead_of_raising(test_workflow):
    a = _analysis(test_workflow, workflow_name="no.such.workflow", kwargs={})
    submit_workflow(a, True)
    a.refresh_from_db()
    assert a.task_state == WorkflowResult.FAILURE
    assert "no.such.workflow" in a.task_error
    assert a.execution_handle is None


@pytest.mark.django_db
def test_result_without_handle_belongs_to_celery(test_workflow):
    a = _analysis(test_workflow, execution_handle=None)
    assert manager_for_result(a).name == "celery"


@pytest.mark.django_db
@override_settings(TOPOBANK_WORKFLOW_MANAGERS=[FAKE_PATH])
def test_state_progress_and_cancel_route_to_the_manager_of_the_handle(test_workflow):
    # Launched by the fake manager; polling must go to it even though the
    # Celery manager also knows this workflow
    a = _analysis(
        test_workflow,
        task_state=WorkflowResult.STARTED,
        execution_handle={"manager": "fake", "data": {}},
    )
    assert a.get_celery_state() == WorkflowResult.STARTED
    assert a.get_task_state() == WorkflowResult.STARTED
    assert a.get_task_progress() == 42.0
    assert a.get_task_messages() == ["working"]
    a.cancel_task()
    assert FakeWorkflowManager.cancelled == [a.pk]


@pytest.mark.django_db
@override_settings(TOPOBANK_WORKFLOW_MANAGERS=[FAKE_PATH])
def test_manager_failure_overrides_self_reported_state(test_workflow):
    a = _analysis(
        test_workflow,
        task_state=WorkflowResult.STARTED,
        execution_handle={"manager": "fake", "data": {}},
    )
    FakeWorkflowManager.state = WorkflowResult.FAILURE
    assert a.get_task_state() == WorkflowResult.FAILURE


@pytest.mark.django_db
def test_set_pending_state_clears_handle(test_workflow):
    a = _analysis(test_workflow, execution_handle={"manager": "fake", "data": {}})
    a.set_pending_state()
    a.refresh_from_db()
    assert a.execution_handle is None
    assert a.task_state == WorkflowResult.PENDING


# ---------------------------------------------------------------------------
# Status contract
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_started_report_sets_start_time(test_workflow):
    a = _analysis(
        test_workflow,
        task_state=WorkflowResult.PENDING,
        task_start_time=None,
        task_end_time=None,
    )
    assert apply_status_report(a, StatusReport(state=WorkflowResult.STARTED))
    a.refresh_from_db()
    assert a.task_state == WorkflowResult.STARTED
    assert a.task_start_time is not None
    assert a.task_end_time is None


@pytest.mark.django_db
def test_claim_is_won_exactly_once(test_workflow):
    a = _analysis(test_workflow, task_state=WorkflowResult.PENDING)
    b = WorkflowResult.objects.get(pk=a.pk)  # a second worker's view of the row
    assert apply_status_report(a, StatusReport(state=WorkflowResult.STARTED), claim=True)
    assert not apply_status_report(b, StatusReport(state=WorkflowResult.STARTED), claim=True)
    # The loser sees the winner's state, not its own optimistic one
    assert b.task_state == WorkflowResult.STARTED


@pytest.mark.django_db
def test_claim_is_refused_on_a_finished_row(test_workflow):
    a = _analysis(test_workflow, task_state=WorkflowResult.SUCCESS)
    assert not apply_status_report(a, StatusReport(state=WorkflowResult.STARTED), claim=True)
    a.refresh_from_db()
    assert a.task_state == WorkflowResult.SUCCESS


@pytest.mark.django_db
def test_success_report_records_outcome(test_workflow):
    a = _analysis(test_workflow, task_state=WorkflowResult.STARTED)
    apply_status_report(
        a,
        StatusReport(
            state=WorkflowResult.SUCCESS,
            memory=12345,
            timer={"timers": {"x": 1.0}},
            dois=["10.1000/xyz"],
        ),
    )
    a.refresh_from_db()
    assert a.task_state == WorkflowResult.SUCCESS
    assert a.task_end_time is not None
    assert a.task_memory == 12345
    assert a.task_timer == {"timers": {"x": 1.0}}
    assert a.dois == ["10.1000/xyz"]


@pytest.mark.django_db
def test_failure_report_records_error_and_strips_nul(test_workflow):
    a = _analysis(test_workflow, task_state=WorkflowResult.STARTED)
    apply_status_report(
        a, StatusReport(state=WorkflowResult.FAILURE, error="boom\x00", traceback="tb\x00")
    )
    a.refresh_from_db()
    assert a.task_state == WorkflowResult.FAILURE
    assert a.task_error == "boom"
    assert a.task_traceback == "tb"
    assert a.task_end_time is not None


@pytest.mark.django_db
def test_files_in_a_success_report_become_manifests(test_workflow):
    a = _analysis(test_workflow, task_state=WorkflowResult.STARTED)
    files = [
        FileEntry(
            filename="model.nc",
            path=f"{a.storage_prefix}/model.nc",
            size_bytes=10,
            content_type="application/x-netcdf",
        ),
        FileEntry(filename="result.json", path=f"{a.storage_prefix}/result.json"),
    ]
    apply_status_report(a, StatusReport(state=WorkflowResult.SUCCESS, files=files))
    names = {m.filename: m for m in a.folder.get_valid_files()}
    assert set(names) >= {"model.nc", "result.json"}
    assert names["model.nc"].file.name == f"{a.storage_prefix}/model.nc"
    assert names["model.nc"].size_bytes == 10
    assert names["model.nc"].content_type == "application/x-netcdf"
    assert names["model.nc"].kind == "der"
    assert names["model.nc"].permissions == a.folder.permissions
    # Registering again is idempotent
    apply_status_report(a, StatusReport(state=WorkflowResult.SUCCESS, files=files))
    assert a.folder.files.filter(filename="model.nc").count() == 1


_HOOK_CALLS = []


def _hook(instance, report):
    _HOOK_CALLS.append((instance.pk, report.state))


@pytest.mark.django_db
@override_settings(TOPOBANK_TASK_LIFECYCLE_HOOKS=[f"{__name__}._hook"])
def test_lifecycle_hooks_fire_on_every_report(test_workflow):
    _HOOK_CALLS.clear()
    a = _analysis(test_workflow, task_state=WorkflowResult.PENDING)
    apply_status_report(a, StatusReport(state=WorkflowResult.STARTED))
    apply_status_report(a, StatusReport(state=WorkflowResult.SUCCESS))
    assert _HOOK_CALLS == [(a.pk, WorkflowResult.STARTED), (a.pk, WorkflowResult.SUCCESS)]


@pytest.mark.django_db
@override_settings(TOPOBANK_TASK_LIFECYCLE_HOOKS=["os.path.no_such_hook"])
def test_failing_hook_does_not_block_the_report(test_workflow):
    a = _analysis(test_workflow, task_state=WorkflowResult.PENDING)
    apply_status_report(a, StatusReport(state=WorkflowResult.SUCCESS))
    a.refresh_from_db()
    assert a.task_state == WorkflowResult.SUCCESS


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
def test_get_celery_queue_is_the_mapped_default_queue(test_workflow, settings):
    a = _analysis(test_workflow)
    settings.CELERY_LOGICAL_QUEUE_MAP = {settings.TOPOBANK_ANALYSIS_QUEUE: "mapped"}
    assert a.get_celery_queue() == "mapped"
