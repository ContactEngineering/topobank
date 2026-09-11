"""
Tests for how a workflow result's files are registered: reservation at
launch, provisional writes, settlement by the success report, incremental
and failure reports, re-runs and the custodian.
"""

import datetime

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

import topobank.testing.workflows  # noqa: F401
from topobank.analysis.custodian import periodic_cleanup
from topobank.analysis.models import Workflow, WorkflowResult
from topobank.analysis.status import ManifestEntry, StatusReport, apply_status_report
from topobank.analysis.tasks import perform_analysis
from topobank.files.models import Manifest
from topobank.testing.factories import Topography1DFactory, TopographyAnalysisFactory

WITH_OUTPUTS = "topobank.testing.test_with_outputs"
MISSING_OUTPUT = "topobank.testing.test_missing_output"


def _pending(workflow_name, **overrides):
    params = dict(
        workflow_name=workflow_name,
        kwargs=Workflow(name=workflow_name).get_default_kwargs(),
        task_state=WorkflowResult.PENDING,
        task_start_time=None,
        task_end_time=None,
    )
    params.update(overrides)
    analysis = TopographyAnalysisFactory(**params)
    analysis.folder.remove_files()
    return analysis


def _names(qs):
    return set(qs.values_list("filename", flat=True))


# ---------------------------------------------------------------------------
# Reservation and provisional writes
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_result_folders_write_provisionally():
    analysis = _pending(WITH_OUTPUTS)
    assert analysis.folder.provisional_writes
    analysis.folder.save_file("x.json", "der", ContentFile(b"{}"))
    assert _names(analysis.folder.get_provisional_files()) == {"x.json"}
    assert analysis.folder.get_valid_files().count() == 0


@pytest.mark.django_db
def test_declared_outputs_are_reserved_before_launch():
    analysis = _pending(WITH_OUTPUTS)
    assert set(analysis.declared_outputs()) == {"model.nc", "metadata.json"}

    reserved = analysis.reserve_declared_outputs()

    assert {m.filename for m in reserved} == {"model.nc", "metadata.json"}
    assert _names(analysis.folder.get_provisional_files()) == {"model.nc", "metadata.json"}
    assert all(not m.file for m in reserved)
    # Idempotent
    analysis.reserve_declared_outputs()
    assert analysis.folder.files.count() == 2


@pytest.mark.django_db
def test_workflows_without_declared_outputs_reserve_nothing(test_workflow):
    analysis = _pending(test_workflow.name)
    assert analysis.declared_outputs() == {}
    assert analysis.reserve_declared_outputs() == []
    assert analysis.folder.files.count() == 0


# ---------------------------------------------------------------------------
# Settlement by the terminal report
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_in_process_run_settles_its_files_on_success():
    """The Celery engine end to end: reserve, write provisionally, confirm."""
    analysis = _pending(WITH_OUTPUTS)

    perform_analysis.apply(args=(analysis.id, False))

    analysis.refresh_from_db()
    assert analysis.task_state == WorkflowResult.SUCCESS, analysis.task_error
    valid = _names(analysis.folder.get_valid_files())
    assert "model.nc" in valid
    assert "result.json" in valid
    # The optional output was reserved but never written: dropped, not confirmed
    assert "metadata.json" not in _names(analysis.folder.files)
    assert analysis.folder.get_provisional_files().count() == 0
    assert analysis.has_result_file


@pytest.mark.django_db
def test_missing_declared_output_turns_success_into_failure():
    analysis = _pending(MISSING_OUTPUT)

    perform_analysis.apply(args=(analysis.id, False))

    analysis.refresh_from_db()
    assert analysis.task_state == WorkflowResult.FAILURE
    assert "model.nc" in analysis.task_error
    assert analysis.task_end_time is not None
    # What the run did write is kept, provisionally, as the record of the attempt
    assert "result.json" in _names(analysis.folder.get_provisional_files())
    assert not analysis.has_result_file


@pytest.mark.django_db
def test_success_with_a_file_list_confirms_it_and_drops_the_rest(test_workflow):
    """An engine that reports everything at the end."""
    analysis = _pending(test_workflow.name, task_state=WorkflowResult.STARTED)
    analysis.folder.reserve("never-written.nc")
    analysis.folder.save_file("unreported.json", "der", ContentFile(b"{}"))
    files = [ManifestEntry(filename="result.json", path=f"{analysis.storage_prefix}/result.json")]

    apply_status_report(analysis, StatusReport(state=WorkflowResult.SUCCESS, files=files))

    analysis.refresh_from_db()
    assert analysis.task_state == WorkflowResult.SUCCESS
    assert _names(analysis.folder.get_valid_files()) == {"result.json"}
    assert analysis.folder.get_provisional_files().count() == 0


@pytest.mark.django_db
def test_success_without_a_file_list_confirms_what_was_recorded(test_workflow):
    """An engine that wrote in-process or reported incrementally."""
    analysis = _pending(test_workflow.name, task_state=WorkflowResult.STARTED)
    analysis.folder.reserve("never-written.nc")
    analysis.folder.save_file("written.json", "der", ContentFile(b"{}"))

    apply_status_report(analysis, StatusReport(state=WorkflowResult.SUCCESS))

    assert _names(analysis.folder.get_valid_files()) == {"written.json"}
    assert not analysis.folder.files.filter(filename="never-written.nc").exists()


@pytest.mark.django_db
def test_incremental_report_records_files_provisionally_without_changing_state(test_workflow):
    analysis = _pending(test_workflow.name, task_state=WorkflowResult.STARTED)
    analysis.folder.reserve("model.nc")
    files = [ManifestEntry(filename="model.nc", path=f"{analysis.storage_prefix}/model.nc", size_bytes=3)]

    assert apply_status_report(analysis, StatusReport(files=files))

    analysis.refresh_from_db()
    assert analysis.task_state == WorkflowResult.STARTED
    manifest = analysis.folder.files.get(filename="model.nc")
    assert manifest.confirmed_at is None
    assert manifest.file.name == f"{analysis.storage_prefix}/model.nc"
    assert manifest.size_bytes == 3

    # Success without a list then confirms what was reported along the way
    apply_status_report(analysis, StatusReport(state=WorkflowResult.SUCCESS))
    assert _names(analysis.folder.get_valid_files()) == {"model.nc"}


@pytest.mark.django_db
def test_failure_keeps_provisional_files_and_records_reported_ones_provisionally(test_workflow):
    analysis = _pending(test_workflow.name, task_state=WorkflowResult.STARTED)
    analysis.folder.save_file("partial.json", "der", ContentFile(b"{}"))
    files = [ManifestEntry(filename="remote.nc", path=f"{analysis.storage_prefix}/remote.nc")]

    apply_status_report(analysis, StatusReport(state=WorkflowResult.FAILURE, error="boom", files=files))

    analysis.refresh_from_db()
    assert analysis.task_state == WorkflowResult.FAILURE
    assert _names(analysis.folder.get_provisional_files()) == {"partial.json", "remote.nc"}
    assert analysis.folder.get_valid_files().count() == 0


@pytest.mark.django_db
def test_rerun_discards_the_previous_attempts_provisional_files(test_workflow):
    analysis = _pending(test_workflow.name, task_state=WorkflowResult.SUCCESS)
    analysis.folder.save_file("good.json", "der", ContentFile(b"{}"))
    analysis.folder.confirm_all()
    WorkflowResult.objects.filter(pk=analysis.pk).update(task_state=WorkflowResult.FAILURE)
    analysis.refresh_from_db()
    analysis.folder.reserve("never.nc")
    analysis.folder.save_file("partial.json", "der", ContentFile(b"{}"))
    partial_path = analysis.folder.files.get(filename="partial.json").file.name

    analysis.set_pending_state()

    assert _names(analysis.folder.files) == {"good.json"}
    assert not default_storage.exists(partial_path)


# ---------------------------------------------------------------------------
# Custodian
# ---------------------------------------------------------------------------


def _age(manifests, days):
    Manifest.objects.filter(pk__in=[m.pk for m in manifests]).update(
        created_at=timezone.now() - datetime.timedelta(days=days)
    )


@pytest.mark.django_db
def test_custodian_reclaims_provisional_files_of_runs_that_did_not_succeed(test_workflow):
    failed = _pending(test_workflow.name, task_state=WorkflowResult.FAILURE)
    failed.folder.save_file("partial.json", "der", ContentFile(b"{}"))
    failed.folder.reserve("never.nc")
    partial_path = failed.folder.files.get(filename="partial.json").file.name

    running = _pending(test_workflow.name, task_state=WorkflowResult.STARTED)
    running.folder.save_file("in-progress.json", "der", ContentFile(b"{}"))

    fresh = _pending(test_workflow.name, task_state=WorkflowResult.FAILURE)
    fresh.folder.save_file("recent.json", "der", ContentFile(b"{}"))

    _age(failed.folder.files.all(), days=30)
    _age(running.folder.files.all(), days=30)

    periodic_cleanup()

    assert failed.folder.files.count() == 0
    assert not default_storage.exists(partial_path)
    # Still running: left alone, however old
    assert _names(running.folder.files) == {"in-progress.json"}
    # Failed but within the grace period: left alone
    assert _names(fresh.folder.files) == {"recent.json"}


@pytest.mark.django_db
def test_custodian_leaves_confirmed_files_alone(test_workflow):
    analysis = _pending(test_workflow.name, task_state=WorkflowResult.SUCCESS)
    analysis.folder.save_file("result.json", "der", ContentFile(b"{}"))
    analysis.folder.confirm_all()
    _age(analysis.folder.files.all(), days=30)

    periodic_cleanup()

    assert _names(analysis.folder.get_valid_files()) == {"result.json"}


@pytest.mark.django_db
def test_factory_results_have_confirmed_files():
    """The test factories write a result at creation; a SUCCESS result's files are settled."""
    topo = Topography1DFactory()
    analysis = TopographyAnalysisFactory(subject_topography=topo)
    assert analysis.task_state == WorkflowResult.SUCCESS
    assert analysis.has_result_file
    assert analysis.folder.get_provisional_files().count() == 0
