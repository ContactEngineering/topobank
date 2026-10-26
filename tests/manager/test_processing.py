"""Tests for the two halves of processing a measurement.

`processing.inspect_datafile` reads a data file and writes the derived files
without touching the database; `Topography.apply_inspection` records its result.
The result is a contract between the two, which may run in different processes,
so it survives JSON and is checked before anything of it is written.
"""

import datetime
import json
import os
import subprocess
import sys
import threading
import uuid
from unittest import mock

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import connection

from topobank.manager import processing
from topobank.manager.models import (
    Topography,
    post_refresh_cache,
    processing_storage_prefix,
)
from topobank.files.models import Manifest
from topobank.taskapp import custodian
from topobank.taskapp.custodian import find_lost
from topobank.taskapp.models import TaskStateModel
from topobank.taskapp.utils import claim_started, run_task, task_dispatch
from topobank.testing.data import FIXTURE_DATA_DIR
from topobank.testing.factories import Topography1DFactory, Topography2DFactory


class LocalWriter:
    """A writer that needs nothing but a directory."""

    def __init__(self, root):
        self.root = root
        self.keys = []

    def save(self, name, path):
        target = os.path.join(self.root, name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(path, "rb") as src, open(target, "wb") as dst:
            dst.write(src.read())
        self.keys.append(name)
        return {"key": name, "size": os.path.getsize(target)}

    def delete(self, keys=None):
        for key in list(self.keys if keys is None else keys):
            os.remove(os.path.join(self.root, key))
            self.keys.remove(key)


def _parameters(**values):
    defaults = dict(
        name="measurement",
        filename="10x10.txt",
        data_source=None,
        size_x=1.0,
        size_y=1.0,
        unit="nm",
        height_scale=1.0,
        is_periodic=None,
        fill_undefined_data_mode="do-not-fill",
        detrend_mode="center",
        instrument_name="",
        instrument_parameters={},
    )
    defaults.update(values)
    return processing.InspectionParameters(**defaults)


@pytest.fixture
def broker():
    messages = []
    lock = threading.Lock()

    def apply_async(args=None, kwargs=None, task_id=None, **options):
        with lock:
            messages.append((list(args), task_id))

    with mock.patch.object(task_dispatch, "apply_async", side_effect=apply_async):
        yield messages


def _inspect(topo, run=None):
    """Run the compute half on `topo`'s file, as another process would.

    The files go to the folder of `run`, as a backend writes them, or to a fresh
    one.
    """
    writer = processing.StorageWriter(
        default_storage, topo.processing_folder(run or uuid.uuid4().hex)
    )
    with topo.datafile.open("rb") as source:
        result = processing.inspect_datafile(
            source, topo.inspection_parameters(filename=topo.datafile.filename), writer
        )
    return result, writer


#
# The compute half
#


def test_inspection_needs_no_database(tmp_path):
    """No `django_db` mark: any query would fail the test."""
    writer = LocalWriter(str(tmp_path))
    with open(os.path.join(FIXTURE_DATA_DIR, "10x10.txt"), "rb") as source:
        result = processing.inspect_datafile(source, _parameters(), writer)

    assert result.fields["resolution_x"] == 10
    assert result.fields["resolution_y"] == 10
    assert result.derived["thumbnail"]["filename"] == "thumbnail.jpeg"
    assert result.derived["squeezed_datafile"]["filename"] == "10x10-squeezed.nc"
    assert any(f["filename"] == "dzi.json" for f in result.derived["deepzoom"])
    for key in result.written_keys():
        assert os.path.getsize(os.path.join(str(tmp_path), key)) > 0


def test_a_line_scan_has_no_deep_zoom_images(tmp_path):
    writer = LocalWriter(str(tmp_path))
    with open(os.path.join(FIXTURE_DATA_DIR, "line_scan_1.asc"), "rb") as source:
        result = processing.inspect_datafile(
            source, _parameters(filename="line_scan_1.asc", size_y=None), writer
        )

    assert "deepzoom" not in result.derived
    assert result.fields["resolution_y"] is None


def test_incomplete_metadata_writes_no_derived_files(tmp_path):
    writer = LocalWriter(str(tmp_path))
    with open(os.path.join(FIXTURE_DATA_DIR, "10x10.txt"), "rb") as source:
        result = processing.inspect_datafile(
            source, _parameters(size_x=None, size_y=None), writer
        )

    assert result.derived == {}
    assert writer.keys == []
    assert result.fields["size_editable"] is True


def test_a_failed_inspection_carries_what_it_found(tmp_path):
    writer = LocalWriter(str(tmp_path))
    with mock.patch.object(
        processing, "undefined_data_fraction", side_effect=RuntimeError("broken")
    ):
        with open(os.path.join(FIXTURE_DATA_DIR, "10x10.txt"), "rb") as source:
            with pytest.raises(RuntimeError) as info:
                processing.inspect_datafile(source, _parameters(), writer)

    assert info.value.inspection_result.fields["resolution_x"] == 10


def test_the_deep_zoom_images_share_one_folder(tmp_path):
    """The descriptor and its tiles keep their relative layout in storage."""
    writer = LocalWriter(str(tmp_path))
    with open(os.path.join(FIXTURE_DATA_DIR, "10x10.txt"), "rb") as source:
        result = processing.inspect_datafile(source, _parameters(), writer)

    for item in result.derived["deepzoom"]:
        assert item["key"] == f"deepzoom/{item['filename']}"


def test_parameters_survive_json():
    params = _parameters(visualization_detrend_mode="height")

    restored = processing.InspectionParameters.from_dict(
        json.loads(json.dumps(params.to_dict()))
    )

    assert restored == params


def test_processing_imports_without_django():
    env = {k: v for k, v in os.environ.items() if k != "DJANGO_SETTINGS_MODULE"}
    loaded = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, topobank.manager.processing; "
            "print(sorted(m for m in ('celery', 'django') if m in sys.modules))",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert loaded.stdout.strip() == "[]"


def test_a_first_inspection_reads_with_the_instrument_of_the_file(tmp_path):
    """The tip radius the file gives determines the reliability cutoff."""
    writer = LocalWriter(str(tmp_path))
    params = _parameters(
        filename="dektak-1.csv", data_source=None, size_x=None, size_y=None,
        unit=None,
    )
    with open(os.path.join(FIXTURE_DATA_DIR, "dektak-1.csv"), "rb") as source:
        result = processing.inspect_datafile(source, params, writer)

    assert result.fields["instrument_type"] == "contact-based"
    assert result.fields["short_reliability_cutoff"] is not None


def test_the_written_names_are_cleaned_like_uploads(tmp_path):
    writer = processing.StorageWriter(
        default_storage, f"{processing_storage_prefix()}/{uuid.uuid4().hex}"
    )
    path = tmp_path / "squeezed.nc"
    path.write_bytes(b"netcdf")

    written = writer.save("squeezed/scan #3 (Ø)-squeezed.nc", str(path))

    assert written["key"].endswith("/squeezed/scan_3_Ø-squeezed.nc")
    writer.delete()


def test_a_stream_that_was_read_already_is_read_from_the_start(tmp_path):
    writer = LocalWriter(str(tmp_path))
    with open(os.path.join(FIXTURE_DATA_DIR, "10x10.txt"), "rb") as source:
        source.read()
        result = processing.inspect_datafile(source, _parameters(), writer)

    assert result.fields["resolution_x"] == 10


#
# The apply half
#


@pytest.mark.django_db(transaction=True)
def test_the_derived_files_are_referenced_where_they_were_written(broker, written):
    topo = Topography2DFactory(size_x=1, size_y=1)
    written.clear()

    topo.refresh_cache()

    stored = Topography.objects.get(pk=topo.pk)
    prefix = processing_storage_prefix()
    names = [stored.thumbnail.file.name, stored.squeezed_datafile.file.name]
    names += [m.file.name for m in stored.deepzoom.files.all()]
    assert sorted(names) == sorted(written)
    assert all(name.startswith(f"{prefix}/") for name in names)
    assert stored.squeezed_datafile.size_bytes == stored.squeezed_datafile.file.size
    assert stored.thumbnail.confirmed_at is not None


@pytest.fixture
def written():
    keys = []
    real_save = processing.StorageWriter.save

    def save(self, name, path):
        info = real_save(self, name, path)
        keys.append(info["key"])
        return info

    with mock.patch.object(processing.StorageWriter, "save", save):
        yield keys


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "tamper",
    [
        pytest.param(lambda r: setattr(r, "version", 2), id="version"),
        pytest.param(lambda r: r.fields.update(task_state="su"), id="task field"),
        pytest.param(lambda r: r.fields.update(name="renamed"), id="user field"),
        pytest.param(
            lambda r: r.derived.update(attachments=None), id="unknown derived file"
        ),
        pytest.param(
            lambda r: r.derived["thumbnail"].update(key="uploads/1/raw.txt"),
            id="key outside the prefix",
        ),
        pytest.param(
            lambda r: r.derived["thumbnail"].update(
                key=r.derived["thumbnail"]["key"].rsplit("/thumbnail/", 1)[0]
                + "/../../uploads/1/raw.txt"
            ),
            id="key escaping the prefix",
        ),
        pytest.param(
            lambda r: r.derived["squeezed_datafile"].update(
                key=r.derived["thumbnail"]["key"]
            ),
            id="one key for two files",
        ),
        pytest.param(
            lambda r: r.derived.update(thumbnail={"filename": "thumbnail.jpeg"}),
            id="file without a key",
        ),
        pytest.param(
            lambda r: r.derived["thumbnail"].update(filename="t" * 256),
            id="file name too long",
        ),
        pytest.param(
            lambda r: r.derived["thumbnail"].update(size=-1), id="negative size"
        ),
    ],
)
def test_a_result_is_checked_before_anything_is_written(broker, tamper):
    topo = Topography1DFactory()
    before = Topography.objects.filter(pk=topo.pk).values().get()
    result, writer = _inspect(Topography.objects.get(pk=topo.pk))
    tamper(result)

    with pytest.raises(ValueError):
        Topography.objects.get(pk=topo.pk).apply_inspection(
            result, prefix=writer.prefix
        )

    assert Topography.objects.filter(pk=topo.pk).values().get() == before
    writer.delete()


#
# Runs on a processing backend
#


backend_calls = []


def recording_backend(topography, task_id):
    backend_calls.append(
        (topography.pk, task_id, topography.task_state, connection.in_atomic_block)
    )


def refusing_backend(topography, task_id):
    raise OSError("function not found")


@pytest.fixture
def backend(settings):
    settings.TOPOBANK_PROCESSING_BACKEND = (
        "tests.manager.test_processing.recording_backend"
    )
    backend_calls.clear()
    yield backend_calls


def _start(topo, **kwargs):
    """Dispatch the processing of `topo` to the backend; returns the run's id."""
    assert run_task(Topography.objects.get(pk=topo.pk), **kwargs)
    return backend_calls[-1][1]


@pytest.mark.django_db(transaction=True)
def test_a_backend_gets_the_started_run(broker, backend):
    topo = Topography1DFactory()
    broker.clear()

    task_id = _start(topo)

    stored = Topography.objects.get(pk=topo.pk)
    assert backend == [(topo.pk, str(stored.task_id), TaskStateModel.STARTED, False)]
    assert task_id == str(stored.task_id)
    assert stored.task_state == TaskStateModel.STARTED
    assert stored.task_start_time is not None
    # ...and the Celery task was not sent
    assert broker == []


@pytest.mark.django_db(transaction=True)
def test_a_result_that_went_through_json_applies_like_one_that_did_not(
    broker, backend
):
    """A first inspection, which takes the date and instrument from the file."""
    inline = Topography2DFactory(filename="example3.di")
    remote = Topography2DFactory(filename="example3.di")
    Topography.objects.filter(pk__in=[inline.pk, remote.pk]).update(
        data_source=None, resolution_x=None, bandwidth_lower=None,
        measurement_date=None, instrument_name="",
    )
    inline.refresh_from_db()
    inline.refresh_cache()
    task_id = _start(remote)
    result, _ = _inspect(Topography.objects.get(pk=remote.pk), run=task_id)
    restored = processing.InspectionResult.from_dict(
        json.loads(json.dumps(result.to_dict()))
    )

    assert Topography.objects.get(pk=remote.pk).apply_backend_result(task_id, restored)

    a = Topography.objects.get(pk=inline.pk)
    b = Topography.objects.get(pk=remote.pk)
    assert a.measurement_date == datetime.date(2014, 12, 15)
    assert a.instrument_name == "Dimension Icon"
    for name in processing.INSPECTED_FIELDS:
        assert getattr(a, name) == getattr(b, name), name
    assert len(b.deepzoom) == len(a.deepzoom) > 0
    assert b.thumbnail.file.read() == a.thumbnail.file.read()


@pytest.mark.django_db(transaction=True)
def test_a_backend_result_ends_the_run(broker, backend):
    topo = Topography1DFactory()
    # A first inspection, which sets significant fields (`data_source`)
    Topography.objects.filter(pk=topo.pk).update(data_source=None, resolution_x=None)
    task_id = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=task_id)
    refreshed = []

    def receiver(sender, instance, **kwargs):
        refreshed.append(instance.pk)

    post_refresh_cache.connect(receiver, sender=Topography)
    try:
        assert Topography.objects.get(pk=topo.pk).apply_backend_result(task_id, result)
    finally:
        post_refresh_cache.disconnect(receiver, sender=Topography)

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.resolution_x is not None
    assert stored.data_source == 0
    assert stored.task_state == TaskStateModel.SUCCESS
    assert str(stored.task_id) == task_id
    assert stored.task_end_time > stored.task_start_time
    assert stored.task_error == ""
    assert refreshed == [topo.pk]
    # Recording what the run found is not an edit that dispatches it again
    assert len(backend) == 1
    assert broker == []


@pytest.mark.django_db(transaction=True)
def test_a_failed_backend_run_ends_as_a_failure(broker, backend):
    topo = Topography1DFactory()
    old_ids = (topo.thumbnail_id, topo.squeezed_datafile_id)
    Topography.objects.filter(pk=topo.pk).update(resolution_x=None)
    task_id = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=task_id)

    assert Topography.objects.get(pk=topo.pk).apply_backend_result(
        task_id, result, error="out of memory", traceback="Traceback (remote)"
    )

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.FAILURE
    assert stored.task_error == "out of memory"
    assert stored.task_traceback == "Traceback (remote)"
    # What it found is recorded; its files are not
    assert stored.resolution_x is not None
    assert (stored.thumbnail_id, stored.squeezed_datafile_id) == old_ids
    assert not any(default_storage.exists(key) for key in result.written_keys())
    assert len(backend) == 1


@pytest.mark.django_db(transaction=True)
def test_a_backend_run_can_fail_without_a_result(broker, backend):
    topo = Topography1DFactory()
    task_id = _start(topo)

    assert Topography.objects.get(pk=topo.pk).apply_backend_result(
        task_id, error="the function timed out"
    )

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.FAILURE
    assert stored.task_error == "the function timed out"


@pytest.mark.django_db(transaction=True)
def test_a_backend_result_must_lie_in_the_folder_of_its_run(broker, backend):
    """Files of another run (another measurement's, say) cannot be claimed."""
    topo = Topography1DFactory()
    old_ids = (topo.thumbnail_id, topo.squeezed_datafile_id)
    task_id = _start(topo)
    result, writer = _inspect(Topography.objects.get(pk=topo.pk), run="another-run")

    with pytest.raises(ValueError):
        Topography.objects.get(pk=topo.pk).apply_backend_result(task_id, result)

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.FAILURE
    assert (stored.thumbnail_id, stored.squeezed_datafile_id) == old_ids
    # ...and the other run's files are left alone
    assert all(default_storage.exists(key) for key in result.written_keys())
    writer.delete()


@pytest.mark.django_db(transaction=True)
def test_an_edit_during_a_backend_run_supersedes_it(broker, backend):
    topo = Topography1DFactory(detrend_mode="center")
    old_ids = (topo.thumbnail_id, topo.squeezed_datafile_id)
    task_id = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=task_id)

    edited = Topography.objects.get(pk=topo.pk)
    edited.detrend_mode = "height"
    edited.save()

    # The edit dispatched the processing again, with the new setting
    assert len(backend) == 2
    rerun = backend[-1][1]
    assert rerun != task_id
    # ...and the result of the stale run is not recorded
    assert not Topography.objects.get(pk=topo.pk).apply_backend_result(task_id, result)
    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.STARTED
    assert str(stored.task_id) == rerun
    assert stored.detrend_mode == "height"
    assert (stored.thumbnail_id, stored.squeezed_datafile_id) == old_ids
    assert not any(default_storage.exists(key) for key in result.written_keys())


@pytest.mark.django_db(transaction=True)
def test_a_late_result_of_a_replaced_run_is_discarded(broker, backend):
    topo = Topography1DFactory()
    old_ids = (topo.thumbnail_id, topo.squeezed_datafile_id)
    replaced = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=replaced)
    # A forced recompute claims the measurement before the result comes back
    _start(topo, force=True)

    assert not Topography.objects.get(pk=topo.pk).apply_backend_result(
        replaced, result
    )

    stored = Topography.objects.get(pk=topo.pk)
    assert (stored.thumbnail_id, stored.squeezed_datafile_id) == old_ids
    assert not any(default_storage.exists(key) for key in result.written_keys())


@pytest.mark.django_db(transaction=True)
def test_a_result_delivered_twice_is_recorded_once(broker, backend):
    topo = Topography1DFactory()
    task_id = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=task_id)
    assert Topography.objects.get(pk=topo.pk).apply_backend_result(task_id, result)
    applied = Topography.objects.get(pk=topo.pk)

    # The same run, which has ended, and the same files
    assert not Topography.objects.get(pk=topo.pk).apply_backend_result(
        task_id, result
    )

    again = Topography.objects.get(pk=topo.pk)
    assert again.thumbnail_id == applied.thumbnail_id
    assert again.squeezed_datafile_id == applied.squeezed_datafile_id
    assert again.task_end_time == applied.task_end_time
    assert all(default_storage.exists(key) for key in result.written_keys())


@pytest.mark.django_db(transaction=True)
def test_a_late_redelivery_of_an_applied_result_keeps_its_files(broker, backend):
    topo = Topography1DFactory()
    task_id = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=task_id)
    assert Topography.objects.get(pk=topo.pk).apply_backend_result(task_id, result)
    # A forced recompute claims the measurement, and the applied result is then
    # delivered once more
    _start(topo, force=True)

    assert not Topography.objects.get(pk=topo.pk).apply_backend_result(
        task_id, result
    )

    # The files are still the measurement's until the new run replaces them
    stored = Topography.objects.get(pk=topo.pk)
    assert stored.thumbnail.file.name in result.written_keys()
    assert all(default_storage.exists(key) for key in result.written_keys())


@pytest.mark.django_db(transaction=True)
def test_a_run_a_worker_holds_is_not_lost_once_a_backend_is_configured(
    broker, backend
):
    """A Celery run already under way when the backend was switched on."""
    topo = Topography1DFactory()
    task_id = _start(topo)

    held = find_lost(live={task_id}, min_age=datetime.timedelta(0))
    not_held = find_lost(live=set(), min_age=datetime.timedelta(0))

    assert topo.pk not in [obj.pk for obj in held if isinstance(obj, Topography)]
    assert topo.pk in [obj.pk for obj in not_held if isinstance(obj, Topography)]


@pytest.mark.django_db(transaction=True)
def test_a_backend_that_fails_to_start_fails_the_measurement(broker, settings):
    settings.TOPOBANK_PROCESSING_BACKEND = (
        "tests.manager.test_processing.refusing_backend"
    )
    topo = Topography1DFactory()

    # The request that dispatched the run carries on
    assert run_task(topo)

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.FAILURE
    assert "function not found" in stored.task_error
    assert "OSError" in stored.task_traceback


@pytest.mark.django_db(transaction=True)
def test_a_backend_that_cannot_be_loaded_fails_the_measurement(broker, settings):
    settings.TOPOBANK_PROCESSING_BACKEND = "tests.manager.test_processing.no_such_backend"
    topo = Topography1DFactory()

    with pytest.raises(ImportError):
        run_task(topo)

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.FAILURE
    assert "no_such_backend" in stored.task_error


@pytest.mark.django_db(transaction=True)
def test_a_backend_refuses_task_arguments(broker, backend):
    topo = Topography1DFactory()

    with pytest.raises(TypeError):
        run_task(topo, None, "an argument")

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.FAILURE
    assert backend == []


@pytest.mark.django_db(transaction=True)
def test_without_a_backend_the_celery_task_is_sent(broker, settings):
    settings.TOPOBANK_PROCESSING_BACKEND = None
    topo = Topography1DFactory()
    broker.clear()

    assert run_task(topo)

    assert len(broker) == 1


@pytest.mark.django_db(transaction=True)
def test_a_backend_result_that_cannot_be_recorded_leaves_no_files(broker, backend):
    topo = Topography1DFactory()
    old_ids = (topo.thumbnail_id, topo.squeezed_datafile_id)
    task_id = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=task_id)

    with mock.patch.object(
        Topography, "_save_inspection", side_effect=RuntimeError("deadlock detected")
    ):
        with pytest.raises(RuntimeError):
            Topography.objects.get(pk=topo.pk).apply_backend_result(task_id, result)

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.FAILURE
    assert (stored.thumbnail_id, stored.squeezed_datafile_id) == old_ids
    assert not any(default_storage.exists(key) for key in result.written_keys())


@pytest.mark.django_db(transaction=True)
def test_a_result_of_another_version_fails_the_run_and_leaves_no_files(
    broker, backend
):
    """As a backend running other code during a rolling deploy hands back."""
    topo = Topography1DFactory()
    task_id = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=task_id)
    result.version += 1

    with pytest.raises(ValueError):
        Topography.objects.get(pk=topo.pk).apply_backend_result(task_id, result)

    assert Topography.objects.get(pk=topo.pk).task_state == TaskStateModel.FAILURE
    assert not any(default_storage.exists(key) for key in result.written_keys())


@pytest.mark.django_db(transaction=True)
def test_a_late_result_of_another_version_leaves_no_files(broker, backend):
    topo = Topography1DFactory()
    replaced = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=replaced)
    result.version += 1
    _start(topo, force=True)

    assert not Topography.objects.get(pk=topo.pk).apply_backend_result(
        replaced, result
    )

    assert not any(default_storage.exists(key) for key in result.written_keys())


@pytest.mark.django_db(transaction=True)
def test_a_failed_run_keeps_its_own_error_over_its_partial_result(broker, backend):
    topo = Topography1DFactory()
    task_id = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=task_id)
    result.fields["name"] = "not something an inspection sets"

    assert Topography.objects.get(pk=topo.pk).apply_backend_result(
        task_id, result, error="out of memory"
    )

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.FAILURE
    assert stored.task_error == "out of memory"
    assert stored.name == topo.name
    assert not any(default_storage.exists(key) for key in result.written_keys())


@pytest.mark.django_db(transaction=True)
def test_a_backend_run_reports_no_memory_or_timing_of_an_earlier_run(
    broker, backend
):
    topo = Topography1DFactory()
    Topography.objects.filter(pk=topo.pk).update(
        task_memory=123456, task_timer={"refresh_cache": 1.0}
    )
    task_id = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=task_id)

    assert Topography.objects.get(pk=topo.pk).apply_backend_result(task_id, result)

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_memory is None
    assert stored.task_timer is None


@pytest.mark.django_db(transaction=True)
def test_backend_runs_are_reaped_while_no_worker_answers(broker, backend):
    topo = Topography1DFactory()
    _start(topo)

    with mock.patch.object(custodian, "live_task_ids", return_value=None):
        outcome = custodian.reap_lost_tasks(
            min_age_minutes=0, require_confirmation=False
        )

    assert outcome["failed"] >= 1
    assert Topography.objects.get(pk=topo.pk).task_state == TaskStateModel.FAILURE


@pytest.mark.django_db(transaction=True)
def test_celery_runs_are_not_reaped_while_no_worker_answers(broker, settings):
    settings.TOPOBANK_PROCESSING_BACKEND = None
    topo = Topography1DFactory()
    assert run_task(Topography.objects.get(pk=topo.pk))
    (_, task_id), = broker[-1:]
    assert claim_started(Topography, topo.pk, task_id)

    with mock.patch.object(custodian, "live_task_ids", return_value=None):
        custodian.reap_lost_tasks(min_age_minutes=0, require_confirmation=False)

    assert Topography.objects.get(pk=topo.pk).task_state == TaskStateModel.STARTED


@pytest.mark.django_db(transaction=True)
def test_a_broker_error_after_a_worker_started_the_run_leaves_it_running(settings):
    """`apply_async` can fail after the message went out (a confirm timeout)."""
    settings.TOPOBANK_PROCESSING_BACKEND = None
    topo = Topography1DFactory()

    def deliver_then_fail(args=None, kwargs=None, task_id=None, **options):
        claim_started(Topography, topo.pk, task_id)
        raise TimeoutError("no confirm from the broker")

    with mock.patch.object(task_dispatch, "apply_async", side_effect=deliver_then_fail):
        with pytest.raises(TimeoutError):
            run_task(Topography.objects.get(pk=topo.pk))

    assert Topography.objects.get(pk=topo.pk).task_state == TaskStateModel.STARTED


@pytest.mark.django_db(transaction=True)
def test_an_unsaved_measurement_that_fails_to_save_keeps_no_manifests(broker):
    topo = Topography1DFactory()
    result, writer = _inspect(Topography.objects.get(pk=topo.pk))
    unsaved = Topography(
        surface=topo.surface,
        permissions=topo.permissions,
        created_by=topo.created_by,
        name="unsaved",
    )

    with mock.patch.object(
        Topography, "_save_inspection", side_effect=RuntimeError("constraint")
    ):
        with pytest.raises(RuntimeError):
            unsaved.apply_inspection(result, prefix=writer.prefix)

    assert not Manifest.objects.filter(file__in=result.written_keys()).exists()
    writer.delete()


def _run_folder(topo, task_id):
    return processing.list_keys(default_storage, topo.processing_folder(task_id))


@pytest.mark.django_db(transaction=True)
def test_a_lost_backend_run_leaves_no_files(broker, backend):
    topo = Topography1DFactory()
    task_id = _start(topo)
    _inspect(Topography.objects.get(pk=topo.pk), run=task_id)  # and never reports
    assert _run_folder(topo, task_id)

    with mock.patch.object(custodian, "live_task_ids", return_value=None):
        custodian.reap_lost_tasks(min_age_minutes=0, require_confirmation=False)

    assert Topography.objects.get(pk=topo.pk).task_state == TaskStateModel.FAILURE
    assert _run_folder(topo, task_id) == []


@pytest.mark.django_db(transaction=True)
def test_a_failure_without_a_result_leaves_no_files(broker, backend):
    topo = Topography1DFactory()
    task_id = _start(topo)
    _inspect(Topography.objects.get(pk=topo.pk), run=task_id)

    assert Topography.objects.get(pk=topo.pk).apply_backend_result(
        task_id, error="out of memory"
    )

    assert _run_folder(topo, task_id) == []


@pytest.mark.django_db(transaction=True)
def test_a_result_naming_a_file_that_was_never_stored_is_refused(broker, backend):
    topo = Topography1DFactory()
    old_ids = (topo.thumbnail_id, topo.squeezed_datafile_id)
    task_id = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=task_id)
    result.derived["thumbnail"]["key"] = (
        topo.processing_folder(task_id) + "/thumbnail/never-uploaded.jpeg"
    )

    with pytest.raises(ValueError, match="never stored"):
        Topography.objects.get(pk=topo.pk).apply_backend_result(task_id, result)

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.FAILURE
    assert (stored.thumbnail_id, stored.squeezed_datafile_id) == old_ids
    assert _run_folder(topo, task_id) == []


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "values",
    [
        pytest.param({"unit": "parsec"}, id="unit"),
        pytest.param({"size_x": -1.0}, id="negative size"),
        pytest.param({"instrument_type": "telescope"}, id="instrument type"),
        pytest.param({"height_scale": None}, id="null"),
        pytest.param({"data_source": 3, "channel_names": [["h", "m"]]}, id="channel"),
        pytest.param({"size_x": "wide"}, id="not a number"),
        pytest.param({"unit": ""}, id="blank unit"),
        pytest.param({"instrument_type": ""}, id="blank instrument type"),
    ],
)
def test_a_backend_result_with_impossible_values_is_refused(broker, backend, values):
    topo = Topography1DFactory()
    names = ("unit", "size_x", "instrument_type", "height_scale", "data_source")
    before = Topography.objects.filter(pk=topo.pk).values(*names).get()
    task_id = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=task_id)
    result.fields.update(values)

    with pytest.raises(ValueError):
        Topography.objects.get(pk=topo.pk).apply_backend_result(task_id, result)

    stored = Topography.objects.filter(pk=topo.pk)
    assert stored.values(*names).get() == before
    assert stored.get().task_state == TaskStateModel.FAILURE
    assert _run_folder(topo, task_id) == []


@pytest.mark.django_db(transaction=True)
def test_a_failed_run_keeps_its_error_over_an_impossible_partial_value(
    broker, backend
):
    topo = Topography1DFactory()
    task_id = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=task_id)
    result.fields["size_x"] = "wide"

    assert Topography.objects.get(pk=topo.pk).apply_backend_result(
        task_id, result, error="out of memory"
    )

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_error == "out of memory"
    assert stored.size_x == topo.size_x


@pytest.mark.django_db(transaction=True)
def test_a_malformed_tile_fails_the_run_and_leaves_no_files(broker, backend):
    topo = Topography2DFactory(size_x=1, size_y=1)
    task_id = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=task_id)
    result.derived["deepzoom"].append({"filename": "dzi_files/0/9_9.jpg"})

    with pytest.raises(ValueError):
        Topography.objects.get(pk=topo.pk).apply_backend_result(task_id, result)

    assert Topography.objects.get(pk=topo.pk).task_state == TaskStateModel.FAILURE
    assert _run_folder(topo, task_id) == []


@pytest.mark.django_db(transaction=True)
def test_a_pass_without_workers_keeps_the_suspects_of_the_last_one(broker, backend):
    """It judges backend runs only; the Celery runs it suspected stay suspects."""
    topo = Topography1DFactory()
    task_id = _start(topo)
    custodian.cache.set(custodian.SUSPECT_CACHE_KEY, {"celery-run"}, 60)

    with mock.patch.object(custodian, "live_task_ids", return_value=None):
        custodian.reap_lost_tasks(min_age_minutes=0)

    assert custodian.cache.get(custodian.SUSPECT_CACHE_KEY) == {"celery-run", task_id}


@pytest.mark.django_db(transaction=True)
def test_a_backend_that_cannot_be_loaded_does_not_stop_the_sweep(broker, settings):
    settings.TOPOBANK_PROCESSING_BACKEND = None
    topo = Topography1DFactory()
    assert run_task(Topography.objects.get(pk=topo.pk))
    (_, task_id), = broker[-1:]
    assert claim_started(Topography, topo.pk, task_id)
    settings.TOPOBANK_PROCESSING_BACKEND = "tests.manager.test_processing.no_such"

    lost = find_lost(live=set(), min_age=datetime.timedelta(0))

    assert topo.pk in [obj.pk for obj in lost if isinstance(obj, Topography)]


def test_the_thumbnail_format_has_a_default(settings):
    del settings.TOPOBANK_THUMBNAIL_FORMAT
    topo = Topography(name="measurement", instrument_parameters={})

    assert topo.inspection_parameters().thumbnail_format == "jpeg"


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("task_id", [None, "", "not-a-run"])
def test_a_result_without_a_run_id_is_refused_and_deletes_nothing(
    broker, backend, task_id
):
    other = Topography1DFactory()
    files = [other.thumbnail.file.name, other.squeezed_datafile.file.name]
    topo = Topography1DFactory()
    _start(topo)

    with pytest.raises(ValueError):
        Topography.objects.get(pk=topo.pk).apply_backend_result(
            task_id, error="lost the id"
        )

    assert all(default_storage.exists(name) for name in files)


@pytest.mark.django_db(transaction=True)
def test_a_result_for_another_measurement_leaves_that_measurement_alone(
    broker, backend
):
    a = Topography1DFactory()
    task_id = _start(a)
    result, _ = _inspect(Topography.objects.get(pk=a.pk), run=task_id)
    assert Topography.objects.get(pk=a.pk).apply_backend_result(task_id, result)
    b = Topography1DFactory()

    assert not Topography.objects.get(pk=b.pk).apply_backend_result(task_id, result)

    stored = Topography.objects.get(pk=a.pk)
    assert stored.thumbnail.file.name in result.written_keys()
    assert all(default_storage.exists(key) for key in result.written_keys())


@pytest.mark.django_db(transaction=True)
def test_a_result_after_the_run_was_failed_as_lost_is_not_recorded(broker, backend):
    """The custodian fails the run once its result has been checked."""
    topo = Topography1DFactory()
    old_ids = (topo.thumbnail_id, topo.squeezed_datafile_id)
    task_id = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=task_id)
    real_apply = Topography.apply_inspection

    def lost_meanwhile(self, result, **kwargs):
        assert custodian.mark_lost(Topography.objects.get(pk=topo.pk))
        return real_apply(self, result, **kwargs)

    with mock.patch.object(Topography, "apply_inspection", lost_meanwhile):
        assert not Topography.objects.get(pk=topo.pk).apply_backend_result(
            task_id, result
        )

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.FAILURE
    assert (stored.thumbnail_id, stored.squeezed_datafile_id) == old_ids
    assert not Manifest.objects.filter(file__in=result.written_keys()).exists()
    assert _run_folder(topo, task_id) == []


@pytest.mark.django_db(transaction=True)
def test_cleaning_up_a_run_waits_for_its_result_being_recorded(broker, backend):
    """The custodian, or a second delivery, cleans up while the first records."""
    topo = Topography1DFactory()
    task_id = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=task_id)
    attached = threading.Event()
    proceed = threading.Event()
    real_attach = Topography._attach_derived
    errors = []

    def attach_then_wait(self, result, row):
        retired = real_attach(self, result, row)
        attached.set()
        proceed.wait(10)
        return retired

    def record():
        try:
            with mock.patch.object(Topography, "_attach_derived", attach_then_wait):
                Topography.objects.get(pk=topo.pk).apply_backend_result(
                    task_id, result
                )
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)
        finally:
            connection.close()

    def clean_up():
        try:
            Topography.objects.get(pk=topo.pk).discard_run(task_id)
        finally:
            connection.close()

    recording = threading.Thread(target=record)
    recording.start()
    assert attached.wait(10)
    cleaning = threading.Thread(target=clean_up)
    cleaning.start()
    # The cleanup waits for the row lock the recording holds
    cleaning.join(1)
    assert cleaning.is_alive()
    proceed.set()
    recording.join(10)
    cleaning.join(10)

    assert errors == []
    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.SUCCESS
    assert stored.thumbnail.file.name in result.written_keys()
    assert all(default_storage.exists(key) for key in result.written_keys())


@pytest.mark.django_db(transaction=True)
def test_files_of_the_run_its_result_does_not_name_are_deleted(broker, backend):
    """A retried attempt's leftovers, say."""
    topo = Topography1DFactory()
    task_id = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=task_id)
    leftover = default_storage.save(
        topo.processing_folder(task_id) + "/thumbnail/first-attempt.jpeg",
        ContentFile(b"jpeg"),
    )

    assert Topography.objects.get(pk=topo.pk).apply_backend_result(task_id, result)

    assert not default_storage.exists(leftover)
    assert sorted(_run_folder(topo, task_id)) == sorted(result.written_keys())


@pytest.mark.django_db(transaction=True)
def test_a_failed_run_keeps_its_error_over_a_failure_to_record_its_partial_result(
    broker, backend
):
    topo = Topography1DFactory()
    task_id = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=task_id)

    with mock.patch.object(
        Topography, "_save_inspection", side_effect=RuntimeError("deadlock detected")
    ):
        assert Topography.objects.get(pk=topo.pk).apply_backend_result(
            task_id, result, error="out of memory"
        )

    assert Topography.objects.get(pk=topo.pk).task_error == "out of memory"


@pytest.mark.django_db(transaction=True)
def test_a_result_recorded_twice_in_one_run_keeps_its_files(broker, backend):
    topo = Topography1DFactory()
    task_id = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=task_id)
    prefix = topo.processing_folder(task_id)
    instance = Topography.objects.get(pk=topo.pk)
    ids = []

    def record_twice():
        for _ in range(2):
            assert instance.apply_inspection(result, prefix=prefix)
            ids.append(Topography.objects.get(pk=topo.pk).thumbnail_id)

    assert instance.complete_task(task_id, record_twice)

    assert ids[0] == ids[1]
    assert all(default_storage.exists(key) for key in result.written_keys())


@pytest.mark.django_db(transaction=True)
def test_a_recorded_result_invalidates_analyses_however_the_run_ends(broker, backend):
    """The custodian fails the run between recording its result and its end."""
    topo = Topography1DFactory()
    old_thumbnail = topo.thumbnail_id
    task_id = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=task_id)
    real_apply = Topography.apply_inspection
    refreshed = []

    def then_lost(self, result, **kwargs):
        recorded = real_apply(self, result, **kwargs)
        assert custodian.mark_lost(Topography.objects.get(pk=topo.pk))
        return recorded

    def receiver(sender, instance, **kwargs):
        refreshed.append(instance.pk)

    post_refresh_cache.connect(receiver, sender=Topography)
    try:
        with mock.patch.object(Topography, "apply_inspection", then_lost):
            assert not Topography.objects.get(pk=topo.pk).apply_backend_result(
                task_id, result
            )
    finally:
        post_refresh_cache.disconnect(receiver, sender=Topography)

    stored = Topography.objects.get(pk=topo.pk)
    assert refreshed == [topo.pk]
    assert stored.thumbnail.file.name in result.written_keys()
    assert all(default_storage.exists(key) for key in result.written_keys())
    assert not Manifest.objects.filter(pk=old_thumbnail).exists()


@pytest.mark.django_db(transaction=True)
def test_the_replaced_files_are_deleted_after_the_end_of_the_run_is_recorded(
    broker, backend
):
    topo = Topography1DFactory()
    old_thumbnail = topo.thumbnail_id
    task_id = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=task_id)
    real_save = TaskStateModel._save_task_result
    seen = []

    def save_task_result(self):
        seen.append(Manifest.objects.filter(pk=old_thumbnail).exists())
        return real_save(self)

    with mock.patch.object(TaskStateModel, "_save_task_result", save_task_result):
        assert Topography.objects.get(pk=topo.pk).apply_backend_result(task_id, result)

    assert seen == [True]
    assert not Manifest.objects.filter(pk=old_thumbnail).exists()


@pytest.mark.django_db(transaction=True)
def test_a_lost_run_of_a_deleted_measurement_is_reaped(broker, backend):
    topo = Topography1DFactory()
    task_id = _start(topo)
    _inspect(Topography.objects.get(pk=topo.pk), run=task_id)
    Topography.objects.get(pk=topo.pk).lazy_delete()

    with mock.patch.object(custodian, "live_task_ids", return_value=None):
        custodian.reap_lost_tasks(min_age_minutes=0, require_confirmation=False)

    stored = Topography._base_manager.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.FAILURE
    assert _run_folder(topo, task_id) == []


@pytest.mark.django_db(transaction=True)
def test_a_run_in_progress_is_not_cleaned_up(broker, backend):
    """A delivery that failed before it ended the run, say."""
    topo = Topography1DFactory()
    task_id = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=task_id)

    Topography.objects.get(pk=topo.pk).discard_run(task_id)

    assert all(default_storage.exists(key) for key in result.written_keys())
    assert Topography.objects.get(pk=topo.pk).apply_backend_result(task_id, result)


@pytest.mark.django_db(transaction=True)
def test_a_result_reading_a_channel_without_naming_them_is_refused(broker, backend):
    topo = Topography1DFactory()
    task_id = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=task_id)
    del result.fields["channel_names"]
    result.fields["data_source"] = 99

    with pytest.raises(ValueError):
        Topography.objects.get(pk=topo.pk).apply_backend_result(task_id, result)

    assert Topography.objects.get(pk=topo.pk).data_source == topo.data_source


@pytest.mark.django_db(transaction=True)
def test_a_traceback_that_is_no_text_is_recorded_as_text(broker, backend):
    topo = Topography1DFactory()
    task_id = _start(topo)

    assert Topography.objects.get(pk=topo.pk).apply_backend_result(
        task_id, error="out of memory", traceback=["frame 1", "frame 2"]
    )

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_error == "out of memory"
    assert "frame 1" in stored.task_traceback


def test_listing_a_folder_skips_the_names_a_storage_lists_for_empty_segments():
    class Storage:
        def listdir(self, path):
            return ([".", "", "tiles"], ["a.jpg"]) if path == "run" else ([], ["b.jpg"])

    assert processing.list_keys(Storage(), "run") == ["run/a.jpg", "run/tiles/b.jpg"]


@pytest.mark.django_db(transaction=True)
def test_a_retried_attempt_cannot_touch_the_files_of_the_one_recorded(
    broker, backend
):
    topo = Topography1DFactory()
    task_id = _start(topo)
    folder = topo.processing_folder(task_id)
    params = Topography.objects.get(pk=topo.pk).inspection_parameters(
        filename=topo.datafile.filename
    )

    def attempt():
        writer = processing.StorageWriter(default_storage, f"{folder}/{uuid.uuid4().hex}")
        with topo.datafile.open("rb") as source:
            return processing.inspect_datafile(source, params, writer), writer

    first, _ = attempt()
    assert Topography.objects.get(pk=topo.pk).apply_backend_result(task_id, first)
    # A retry of the same run writes everything once more, then fails and
    # cleans up after itself, and reports late
    second, writer = attempt()
    writer.delete()
    assert not Topography.objects.get(pk=topo.pk).apply_backend_result(
        task_id, error="out of memory"
    )

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.SUCCESS
    assert stored.thumbnail.file.name in first.written_keys()
    assert all(default_storage.exists(key) for key in first.written_keys())
    assert sorted(_run_folder(topo, task_id)) == sorted(first.written_keys())


def test_a_long_file_name_gets_a_squeezed_file_with_a_name_that_fits(tmp_path):
    writer = LocalWriter(str(tmp_path))
    with open(os.path.join(FIXTURE_DATA_DIR, "10x10.txt"), "rb") as source:
        result = processing.inspect_datafile(
            source, _parameters(filename="m" * 250 + ".txt"), writer
        )

    name = result.derived["squeezed_datafile"]["filename"]
    assert len(name) == processing.MAX_FILENAME_LENGTH
    assert name.endswith("-squeezed.nc")


@pytest.mark.django_db(transaction=True)
def test_the_clean_up_can_be_left_to_a_worker(broker, backend):
    topo = Topography1DFactory()
    old_thumbnail = topo.thumbnail_id
    task_id = _start(topo)
    result, _ = _inspect(Topography.objects.get(pk=topo.pk), run=task_id)
    leftover = default_storage.save(
        topo.processing_folder(task_id) + "/thumbnail/first-attempt.jpeg",
        ContentFile(b"jpeg"),
    )
    handed = []

    assert Topography.objects.get(pk=topo.pk).apply_backend_result(
        task_id, result, clean_up=handed.append
    )

    # Recorded, with nothing deleted yet
    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.SUCCESS
    assert stored.thumbnail.file.name in result.written_keys()
    assert Manifest.objects.filter(pk=old_thumbnail).exists()
    assert default_storage.exists(leftover)
    (work_left,) = handed
    assert json.loads(json.dumps(work_left)) == work_left

    Topography.clean_up_run(work_left)
    Topography.clean_up_run(work_left)  # once more, as a redelivered task would

    assert not Manifest.objects.filter(pk=old_thumbnail).exists()
    assert not default_storage.exists(leftover)
    assert all(default_storage.exists(key) for key in result.written_keys())


@pytest.mark.django_db(transaction=True)
def test_the_clean_up_deletes_nothing_in_use_or_uploaded(broker):
    topo = Topography2DFactory(size_x=1, size_y=1)
    files = [
        topo.datafile.file.name,
        topo.thumbnail.file.name,
        *(m.file.name for m in topo.deepzoom.files.all()),
    ]

    Topography.clean_up_run(
        {
            "topography": topo.pk,
            "task_id": str(uuid.uuid4()),
            "manifests": [topo.datafile_id, topo.thumbnail_id],
            "folders": [topo.deepzoom_id, topo.attachments_id],
        }
    )

    stored = Topography.objects.get(pk=topo.pk)
    assert (stored.datafile_id, stored.thumbnail_id) == (topo.datafile_id, topo.thumbnail_id)
    assert (stored.deepzoom_id, stored.attachments_id) == (
        topo.deepzoom_id,
        topo.attachments_id,
    )
    assert all(default_storage.exists(name) for name in files)


@pytest.mark.django_db(transaction=True)
def test_the_clean_up_after_a_deleted_measurement_empties_its_run_folder(
    broker, backend
):
    topo = Topography1DFactory()
    task_id = _start(topo)
    _inspect(Topography.objects.get(pk=topo.pk), run=task_id)
    folder = topo.processing_folder(task_id)
    Topography.objects.filter(pk=topo.pk).delete()

    Topography.clean_up_run(
        {"topography": topo.pk, "task_id": task_id, "manifests": [], "folders": []}
    )

    assert processing.list_keys(default_storage, folder) == []
