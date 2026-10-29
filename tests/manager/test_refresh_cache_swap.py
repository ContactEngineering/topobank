"""Tests for how `refresh_cache` replaces derived files and saves its results.

Reprocessing writes the new squeezed file, thumbnail and deep zoom images first
(`processing.inspect_datafile`), saves the new references, and deletes the old
files only once that save has been committed (`Topography.apply_inspection`). It
writes only the fields it changed, and nothing at all once a newer dispatch has
taken the measurement over; the files it wrote are then deleted.
"""

import contextlib
import json
import threading
import uuid
from unittest import mock

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import JSONField

from topobank.files.models import Manifest, ManifestSet
from topobank.manager import processing
from topobank.manager.models import Topography, processing_storage_prefix
from topobank.taskapp.models import TaskStateModel
from topobank.taskapp.utils import run_task, task_dispatch
from topobank.testing.factories import Topography1DFactory, Topography2DFactory


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


@pytest.fixture
def written():
    """Storage keys of every derived file an inspection writes."""
    keys = []
    real_save = processing.StorageWriter.save

    def save(self, name, path):
        info = real_save(self, name, path)
        keys.append(info["key"])
        return info

    with mock.patch.object(processing.StorageWriter, "save", save):
        yield keys


def _derived_ids(topo):
    return topo.thumbnail_id, topo.deepzoom_id, topo.squeezed_datafile_id


def _all_gone(keys):
    return keys and not any(default_storage.exists(key) for key in keys)


@contextlib.contextmanager
def _after_writing(name, hook):
    """Call `hook(written)` once the derived file `name` has been written."""
    description, write = processing._DERIVED_WRITERS[name]

    def write_then_hook(st_topo, params, writer):
        written = write(st_topo, params, writer)
        hook(written)
        return written

    with mock.patch.dict(
        processing._DERIVED_WRITERS, {name: (description, write_then_hook)}
    ):
        yield


@contextlib.contextmanager
def _failing_to_write(name, exc):
    description, _ = processing._DERIVED_WRITERS[name]

    def fail(st_topo, params, writer):
        raise exc

    with mock.patch.dict(processing._DERIVED_WRITERS, {name: (description, fail)}):
        yield


@pytest.mark.django_db(transaction=True)
def test_old_derived_files_are_deleted_only_after_commit(broker):
    topo = Topography2DFactory(size_x=1, size_y=1)
    old_thumbnail, old_deepzoom, old_squeezed = _derived_ids(topo)
    assert None not in (old_thumbnail, old_deepzoom, old_squeezed)

    with transaction.atomic():
        topo.refresh_cache()
        # The new references are in place...
        assert None not in _derived_ids(topo)
        assert old_squeezed != topo.squeezed_datafile_id
        # ...but until the commit the old files are still there to be read
        assert Manifest.objects.filter(pk=old_squeezed).exists()
        assert Manifest.objects.filter(pk=old_thumbnail).exists()
        assert ManifestSet.objects.filter(pk=old_deepzoom).exists()

    assert not Manifest.objects.filter(pk=old_squeezed).exists()
    assert not Manifest.objects.filter(pk=old_thumbnail).exists()
    assert not ManifestSet.objects.filter(pk=old_deepzoom).exists()
    stored = Topography.objects.get(pk=topo.pk)
    assert _derived_ids(stored) == _derived_ids(topo)


@pytest.mark.django_db(transaction=True)
def test_reader_survives_reprocessing_mid_read(broker):
    topo = Topography1DFactory()
    expected = Topography.objects.get(pk=topo.pk).read().heights()
    # A reader loaded the measurement, including its squeezed file reference...
    reader = Topography.objects.get(pk=topo.pk)
    old_squeezed = reader.squeezed_datafile_id

    # ...and reprocessing replaced (and deleted) that file before it got to read
    Topography.objects.get(pk=topo.pk).refresh_cache()
    assert not Manifest.objects.filter(pk=old_squeezed).exists()

    heights = reader.read().heights()
    assert (heights == expected).all()
    # It followed the new reference without taking it over
    assert reader.squeezed_datafile_id == old_squeezed


@pytest.mark.django_db(transaction=True)
def test_reader_falls_back_to_the_raw_file(broker):
    topo = Topography1DFactory()
    expected = Topography.objects.get(pk=topo.pk).read().heights()
    reader = Topography.objects.get(pk=topo.pk)

    # The squeezed file is gone and nothing replaced it
    Manifest.objects.filter(pk=reader.squeezed_datafile_id).delete()

    assert (reader.read().heights() == expected).all()


@pytest.mark.django_db(transaction=True)
def test_superseded_refresh_discards_its_files(broker, written):
    topo = Topography2DFactory(size_x=1, size_y=1)
    broker.clear()
    old_ids = _derived_ids(topo)
    assert run_task(topo)
    task_id = topo.task_id
    written.clear()

    def get_superseded(_):
        assert run_task(Topography.objects.get(pk=topo.pk), force=True)

    ct = ContentType.objects.get_for_model(Topography)
    with _after_writing("squeezed_datafile", get_superseded):
        task_dispatch.apply(args=[ct.id, topo.pk], task_id=str(task_id)).get()

    stored = Topography.objects.get(pk=topo.pk)
    # The references and files of the previous processing are untouched...
    assert _derived_ids(stored) == old_ids
    assert Manifest.objects.filter(pk=old_ids[0]).exists()
    assert ManifestSet.objects.filter(pk=old_ids[1]).exists()
    assert Manifest.objects.filter(pk=old_ids[2]).exists()
    # ...the files the superseded run wrote are gone...
    assert _all_gone(written)
    # ...and the successor's claim stands
    assert stored.task_state == TaskStateModel.PENDING
    assert stored.task_id != task_id


@pytest.mark.django_db(transaction=True)
def test_failed_refresh_keeps_the_previous_derived_files(broker, written):
    topo = Topography2DFactory(size_x=1, size_y=1)
    old_ids = _derived_ids(topo)
    written.clear()
    real_inspect = processing._inspect

    def inspect_then_fail(*args):
        real_inspect(*args)
        raise RuntimeError("worker lost")

    with mock.patch.object(processing, "_inspect", inspect_then_fail):
        with pytest.raises(RuntimeError):
            topo.refresh_cache()

    assert _derived_ids(topo) == old_ids
    assert _derived_ids(Topography.objects.get(pk=topo.pk)) == old_ids
    assert Manifest.objects.filter(pk=old_ids[0]).exists()
    assert ManifestSet.objects.filter(pk=old_ids[1]).exists()
    assert _all_gone(written)


@pytest.mark.django_db(transaction=True)
def test_edits_made_during_processing_survive(broker):
    topo = Topography1DFactory()
    Topography.objects.filter(pk=topo.pk).update(data_source=None, resolution_x=None)
    topo.refresh_from_db()

    def user_edits(_):
        Topography.objects.filter(pk=topo.pk).update(
            name="renamed meanwhile", description="edited meanwhile"
        )

    with _after_writing("thumbnail", user_edits):
        topo.refresh_cache()

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.name == "renamed meanwhile"
    assert stored.description == "edited meanwhile"
    # ...while what the processing found was saved
    assert stored.data_source is not None
    assert stored.resolution_x is not None


@pytest.mark.django_db(transaction=True)
def test_a_stale_full_save_keeps_what_a_refresh_wrote(broker):
    topo = Topography1DFactory()
    # A request loaded the measurement before it was reprocessed...
    stale = Topography.objects.get(pk=topo.pk)
    old_squeezed = stale.squeezed_datafile_id
    Topography.objects.get(pk=topo.pk).refresh_cache()
    processed = Topography.objects.get(pk=topo.pk)
    assert processed.squeezed_datafile_id != old_squeezed
    assert not Manifest.objects.filter(pk=old_squeezed).exists()

    # ...and saves it in full afterwards, e.g. a rename
    stale.name = "renamed"
    stale.save()

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.name == "renamed"
    # The reference to the deleted file did not come back
    assert _derived_ids(stored) == _derived_ids(processed)


@pytest.mark.django_db(transaction=True)
def test_refresh_cache_persists_everything_it_changed(broker):
    topo = Topography2DFactory(size_x=1, size_y=1)
    Topography.objects.filter(pk=topo.pk).update(
        data_source=None,
        datafile_format=None,
        channel_names=[],
        resolution_x=None,
        resolution_y=None,
        bandwidth_lower=None,
        bandwidth_upper=None,
        detrend_parameters=None,
    )
    topo.refresh_from_db()

    topo.refresh_cache()

    stored = Topography.objects.get(pk=topo.pk)
    for field in Topography._meta.concrete_fields:
        if field.name in Topography._TASK_FIELDS or field.name == "updated_at":
            continue
        in_memory, saved = getattr(topo, field.attname), getattr(stored, field.attname)
        if isinstance(field, JSONField):
            # Tuples come back from the database as lists
            in_memory = json.loads(json.dumps(in_memory))
        assert saved == in_memory, field.name


@pytest.mark.django_db(transaction=True)
def test_task_run_records_success(broker):
    """End to end through the worker: claimed, processed, recorded once."""
    topo = Topography1DFactory()
    broker.clear()
    Topography.objects.filter(pk=topo.pk).update(
        task_state=TaskStateModel.SUCCESS, task_id=uuid.uuid4()
    )
    topo.refresh_from_db()
    assert run_task(topo, force=True)
    (args, task_id), = broker

    task_dispatch.apply(args=args, task_id=task_id).get()

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.SUCCESS
    assert str(stored.task_id) == task_id
    assert stored.squeezed_datafile_id is not None


def test_only_missing_objects_count_as_vanished_files():
    from botocore.exceptions import ClientError

    from topobank.manager.models import _is_missing_file_error

    def client_error(code):
        return ClientError({"Error": {"Code": code}}, "GetObject")

    assert _is_missing_file_error(client_error("404"))
    assert _is_missing_file_error(client_error("NoSuchKey"))
    # Anything else is a real storage problem and must not be papered over
    assert not _is_missing_file_error(client_error("AccessDenied"))
    assert not _is_missing_file_error(client_error("SlowDown"))
    assert _is_missing_file_error(FileNotFoundError())


@pytest.mark.django_db(transaction=True)
def test_processing_a_copy_leaves_the_original_deep_zoom_alone(broker):
    from topobank.testing.factories import SurfaceFactory

    original = Topography2DFactory(size_x=1, size_y=1)
    deepzoom_id = original.deepzoom_id
    assert deepzoom_id is not None

    copy = original.deepcopy(SurfaceFactory(created_by=original.created_by))
    assert copy.deepzoom_id is None
    copy.refresh_cache()

    assert copy.deepzoom_id not in (None, deepzoom_id)
    assert ManifestSet.objects.filter(pk=deepzoom_id).exists()
    assert Topography.objects.get(pk=original.pk).deepzoom_id == deepzoom_id


@pytest.mark.django_db(transaction=True)
def test_a_failing_cleanup_does_not_mask_the_error(broker):
    topo = Topography1DFactory()
    error = ValueError("the real one")

    with mock.patch(
        "topobank.manager.models.inspect_datafile", side_effect=error
    ), mock.patch.object(
        Topography, "record_failed_inspection", side_effect=RuntimeError("cleanup")
    ):
        with pytest.raises(ValueError, match="the real one"):
            topo.refresh_cache()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("step", processing.DERIVED_NAMES)
def test_running_out_of_time_fails_the_refresh_and_deletes_its_files(
    broker, written, step
):
    """The soft time limit is no problem with the file being generated: it is not
    caught like one, and the files the refresh wrote so far are deleted rather
    than left behind unreferenced."""
    from celery.exceptions import SoftTimeLimitExceeded

    topo = Topography2DFactory(size_x=1, size_y=1)
    old_ids = _derived_ids(topo)
    written.clear()

    def run_out_of_time(_):
        raise SoftTimeLimitExceeded()

    with _after_writing(step, run_out_of_time):
        with pytest.raises(SoftTimeLimitExceeded):
            topo.refresh_cache()

    assert _all_gone(written)
    assert _derived_ids(Topography.objects.get(pk=topo.pk)) == old_ids
    assert Manifest.objects.filter(pk__in=[old_ids[0], old_ids[2]]).count() == 2
    assert ManifestSet.objects.filter(pk=old_ids[1]).exists()


@pytest.mark.django_db(transaction=True)
def test_an_inline_refresh_racing_a_run_leaks_no_files(broker):
    topo = Topography1DFactory()
    broker.clear()
    first_ids = _derived_ids(topo)
    assert run_task(topo)
    inline_ids = []

    def an_inline_refresh_lands(_):
        if not inline_ids:
            inline_ids.append(None)  # only once: the inline refresh comes here too
            inline = Topography.objects.get(pk=topo.pk)
            inline.refresh_cache()
            inline_ids[:] = [inline.thumbnail_id, inline.squeezed_datafile_id]

    ct = ContentType.objects.get_for_model(Topography)
    with _after_writing("squeezed_datafile", an_inline_refresh_lands):
        task_dispatch.apply(args=[ct.id, topo.pk], task_id=str(topo.task_id)).get()

    assert None not in inline_ids
    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.SUCCESS
    live = {stored.thumbnail_id, stored.squeezed_datafile_id}
    replaced = {first_ids[0], first_ids[2], *inline_ids} - live
    assert len(replaced) == 4
    # Every file that is no longer referenced is gone, the inline refresh's too
    assert not Manifest.objects.filter(pk__in=replaced).exists()
    assert Manifest.objects.filter(pk__in=live).count() == 2


@pytest.mark.django_db(transaction=True)
def test_an_inline_refresh_dispatches_no_processing(broker):
    """`refresh_cache` is the processing: neither reading the data file nor
    saving what it found may queue another run."""
    topo = Topography1DFactory()
    Topography.objects.filter(pk=topo.pk).update(
        task_state=TaskStateModel.NOTRUN, task_id=None, resolution_x=None
    )
    topo.refresh_from_db()
    broker.clear()

    topo.refresh_cache()

    assert broker == []
    stored = Topography.objects.get(pk=topo.pk)
    assert stored.resolution_x is not None
    assert stored.task_state == TaskStateModel.NOTRUN

    # The same for a processed measurement whose file now reads differently
    Topography.objects.filter(pk=topo.pk).update(
        task_state=TaskStateModel.SUCCESS, size_x=topo.size_x * 2
    )
    Topography.objects.get(pk=topo.pk).refresh_cache()

    assert broker == []


@pytest.mark.django_db(transaction=True)
def test_a_failed_save_of_the_results_leaks_no_files(broker, written):
    topo = Topography1DFactory()
    old_ids = _derived_ids(topo)
    written.clear()

    with mock.patch.object(
        Topography, "apply_inspection", side_effect=RuntimeError("lock wait timeout")
    ):
        with pytest.raises(RuntimeError, match="lock wait timeout"):
            topo.refresh_cache()

    assert _all_gone(written)
    assert _derived_ids(Topography.objects.get(pk=topo.pk)) == old_ids


@pytest.mark.django_db(transaction=True)
def test_a_measurement_deleted_during_an_inline_refresh_leaks_no_files(
    broker, written
):
    topo = Topography1DFactory()
    written.clear()

    def get_deleted(_):
        Topography.objects.filter(pk=topo.pk).delete()

    with _after_writing("squeezed_datafile", get_deleted):
        topo.refresh_cache()

    assert _all_gone(written)
    assert not Topography.objects.filter(pk=topo.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_a_failed_replacement_retires_the_old_file_once(broker, caplog):
    topo = Topography1DFactory()
    old_squeezed = topo.squeezed_datafile_id

    with _failing_to_write("squeezed_datafile", OSError("storage unavailable")):
        topo.refresh_cache()

    assert Topography.objects.get(pk=topo.pk).squeezed_datafile_id is None
    assert not Manifest.objects.filter(pk=old_squeezed).exists()
    assert "Could not delete derived file" not in caplog.text


@pytest.mark.django_db(transaction=True)
def test_a_run_whose_results_fail_to_save_still_records_what_it_found(broker):
    topo = Topography1DFactory()
    broker.clear()
    Topography.objects.filter(pk=topo.pk).update(
        task_state=TaskStateModel.SUCCESS, task_id=uuid.uuid4(), resolution_x=None
    )
    topo.refresh_from_db()
    assert run_task(topo, force=True)
    (args, task_id), = broker

    with mock.patch.object(
        Topography, "apply_inspection", side_effect=RuntimeError("lock wait timeout")
    ):
        task_dispatch.apply(args=args, task_id=task_id)

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.FAILURE
    assert stored.resolution_x is not None


@pytest.mark.django_db(transaction=True)
def test_a_failed_refresh_deletes_each_of_its_files_once(broker, written):
    topo = Topography2DFactory(size_x=1, size_y=1)
    written.clear()
    real_inspect = processing._inspect
    real_delete_keys = processing.delete_keys
    deleted = []

    def inspect_then_fail(*args):
        real_inspect(*args)
        raise RuntimeError("worker lost")

    def delete_keys(storage, keys):
        keys = list(keys)
        deleted.extend(keys)
        return real_delete_keys(storage, keys)

    # Whichever path deletes (the writer, or `_discard`), and on whichever
    # storage (one key at a time, or a batch)
    with mock.patch.object(processing, "_inspect", inspect_then_fail), \
            mock.patch.object(processing, "delete_keys", delete_keys), \
            mock.patch("topobank.manager.models.delete_keys", delete_keys):
        with pytest.raises(RuntimeError):
            topo.refresh_cache()

    assert sorted(deleted) == sorted(written)
    assert _all_gone(written)


@pytest.mark.django_db(transaction=True)
def test_a_derived_file_that_fails_partway_leaves_no_files(broker, written):
    topo = Topography2DFactory(size_x=1, size_y=1)
    written.clear()

    def descriptor_fails(_):
        raise RuntimeError("could not write dzi.json")

    with _after_writing("deepzoom", descriptor_fails):
        topo.refresh_cache()

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.deepzoom_id is None
    in_use = {stored.thumbnail.file.name, stored.squeezed_datafile.file.name}
    tiles = [key for key in written if key not in in_use]
    assert tiles
    assert _all_gone(tiles)


@pytest.mark.django_db(transaction=True)
def test_a_rolled_back_save_records_what_was_found_without_its_files(broker):
    topo = Topography1DFactory()
    old_ids = _derived_ids(topo)
    broker.clear()
    Topography.objects.filter(pk=topo.pk).update(
        task_state=TaskStateModel.SUCCESS, task_id=uuid.uuid4(), resolution_x=None
    )
    topo.refresh_from_db()
    assert run_task(topo, force=True)
    (args, task_id), = broker
    real_save = Topography._save_inspection
    calls = []

    def deadlock_once(self, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("deadlock detected")
        return real_save(self, **kwargs)

    with mock.patch.object(Topography, "_save_inspection", deadlock_once):
        task_dispatch.apply(args=args, task_id=task_id)

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.FAILURE
    assert stored.resolution_x is not None
    assert _derived_ids(stored) == old_ids


@pytest.mark.django_db(transaction=True)
def test_unreadable_instrument_parameters_do_not_stop_an_incomplete_inspection(
    broker,
):
    topo = Topography2DFactory(size_x=1, size_y=1)
    Topography.objects.filter(pk=topo.pk).update(
        size_x=None, size_y=None, channel_names=[], datafile_format=None,
        instrument_parameters={"resolution": {"value": "not a number"}},
    )
    topo.refresh_from_db()

    topo.refresh_cache()

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.datafile_format is not None
    assert stored.channel_names


@pytest.mark.django_db(transaction=True)
def test_a_single_derived_file_is_written_like_an_inspection_writes_it(broker):
    topo = Topography1DFactory()
    old = topo.squeezed_datafile_id

    topo.make_squeezed(save=True)

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.squeezed_datafile_id != old
    assert stored.squeezed_datafile.file.name.startswith(
        f"{processing_storage_prefix()}/"
    )
    assert stored.squeezed_datafile.size_bytes == stored.squeezed_datafile.file.size
    assert not Manifest.objects.filter(pk=old).exists()


@pytest.mark.django_db(transaction=True)
def test_a_single_derived_file_is_saved_without_a_save_of_the_measurement(broker):
    topo = Topography1DFactory()
    old = topo.thumbnail_id

    topo.make_thumbnail()

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.thumbnail_id == topo.thumbnail_id
    assert stored.thumbnail_id not in (None, old)
    assert not Manifest.objects.filter(pk=old).exists()


@pytest.mark.django_db(transaction=True)
def test_a_derived_file_that_fails_to_be_saved_leaves_the_measurement_as_it_was(
    broker, written
):
    topo = Topography1DFactory()
    old = topo.squeezed_datafile_id
    count = Manifest.objects.count()
    written.clear()

    with mock.patch(
        "django.db.models.Model.save", side_effect=RuntimeError("lock wait timeout")
    ):
        # A failure to save is not swallowed as a failure to generate would be
        with pytest.raises(RuntimeError, match="lock wait timeout"):
            topo.make_squeezed()

    assert topo.squeezed_datafile_id == old
    assert Topography.objects.get(pk=topo.pk).squeezed_datafile_id == old
    assert Manifest.objects.get(pk=old).file.size > 0
    assert Manifest.objects.count() == count
    assert _all_gone(written)


@pytest.mark.django_db(transaction=True)
def test_a_failed_file_whose_old_one_cannot_be_deleted_still_clears_the_field(
    broker, caplog
):
    topo = Topography1DFactory()
    old = topo.thumbnail_id

    with mock.patch.object(
        Topography, "_make_thumbnail", side_effect=OSError("render")
    ), mock.patch.object(Manifest, "delete", side_effect=OSError("storage")):
        topo.make_thumbnail()  # none_on_error: must not raise

    assert Topography.objects.get(pk=topo.pk).thumbnail_id is None
    assert Manifest.objects.filter(pk=old).exists()
    assert "Could not delete derived file" in caplog.text


@pytest.mark.django_db(transaction=True)
def test_a_run_writes_its_files_under_its_task_id(broker):
    topo = Topography1DFactory()
    broker.clear()
    assert run_task(Topography.objects.get(pk=topo.pk), force=True)
    (args, task_id), = broker

    task_dispatch.apply(args=args, task_id=task_id).get()

    stored = Topography.objects.get(pk=topo.pk)
    folder = stored.processing_folder(task_id)
    assert stored.squeezed_datafile.file.name.startswith(f"{folder}/")
    assert stored.thumbnail.file.name.startswith(f"{folder}/")
