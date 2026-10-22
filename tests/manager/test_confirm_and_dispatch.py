"""Tests for confirming an uploaded data file and starting its processing.

An upload is confirmed and processed exactly once, whichever gets to it first:
the storage's notification (`confirm_and_dispatch`), a read of the file
(`Manifest.exists`), or both at the same time. The race runs on real
transactions, with one database connection per thread; only the broker is
replaced.
"""

import os
import tempfile
import threading
import zipfile
from unittest import mock

import pytest
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import connection, transaction

from topobank.files.models import Manifest
from topobank.manager.export_zip import export_container_zip
from topobank.manager.import_zip import import_container_zip
from topobank.manager.models import Topography
from topobank.manager.uploads import confirm_and_dispatch
from topobank.taskapp.models import TaskStateModel
from topobank.taskapp.utils import task_dispatch
from topobank.testing.data import FIXTURE_DATA_DIR
from topobank.testing.factories import (
    SurfaceFactory,
    Topography1DFactory,
    UserFactory,
)


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


def _unprocessed_measurement(uploaded=True):
    """A measurement that was never processed, with a data file whose upload
    has arrived in storage (or not) but was never confirmed."""
    topo = Topography1DFactory()
    manifest = Manifest.objects.create(
        permissions=topo.permissions, filename=topo.datafile.filename, kind="raw"
    )
    if uploaded:
        with open(f"{FIXTURE_DATA_DIR}/{manifest.filename}", "rb") as fobj:
            stored_as = default_storage.save(manifest.generate_storage_path(), File(fobj))
        assert stored_as == manifest.generate_storage_path()
    Topography.objects.filter(pk=topo.pk).update(
        datafile=manifest, task_state=TaskStateModel.NOTRUN, task_id=None
    )
    return Topography.objects.get(pk=topo.pk)


@pytest.mark.django_db(transaction=True)
def test_reading_an_arrived_upload_confirms_it_and_starts_processing(broker):
    topo = _unprocessed_measurement()
    broker.clear()

    assert topo.datafile.exists()

    manifest = Manifest.objects.get(pk=topo.datafile_id)
    assert manifest.confirmed_at is not None
    assert manifest.file
    assert manifest.size_bytes == manifest.file.size > 0
    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.PENDING
    assert broker == [([mock.ANY, topo.pk], str(stored.task_id))]


@pytest.mark.django_db(transaction=True)
def test_the_notification_confirms_and_starts_processing_once(broker):
    topo = _unprocessed_measurement()
    broker.clear()

    dispatched = confirm_and_dispatch(Manifest.objects.get(pk=topo.datafile_id))
    assert [t.pk for t in dispatched] == [topo.pk]
    first = Manifest.objects.get(pk=topo.datafile_id)
    # A repeated notification changes nothing, and dispatches nothing
    assert confirm_and_dispatch(Manifest.objects.get(pk=topo.datafile_id)) == []

    assert Manifest.objects.get(pk=topo.datafile_id).confirmed_at == first.confirmed_at
    assert len(broker) == 1
    assert Topography.objects.get(pk=topo.pk).task_state == TaskStateModel.PENDING


@pytest.mark.django_db(transaction=True)
def test_a_read_racing_the_notification_confirms_and_processes_once(broker):
    topo = _unprocessed_measurement()
    broker.clear()

    def read_or_notify(i):
        manifest = Manifest.objects.get(pk=topo.datafile_id)
        if i % 2:
            return manifest.exists()
        return confirm_and_dispatch(manifest) is not None

    assert _in_threads(6, read_or_notify) == [True] * 6

    manifest = Manifest.objects.get(pk=topo.datafile_id)
    assert manifest.confirmed_at is not None
    assert len(broker) == 1
    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.PENDING
    assert broker[0][1] == str(stored.task_id)


@pytest.mark.django_db(transaction=True)
def test_a_read_of_a_stranded_measurement_starts_its_processing(broker):
    # Confirmed earlier without ever being dispatched
    topo = _unprocessed_measurement()
    assert topo.datafile.confirm_upload()
    confirmed_at = Manifest.objects.get(pk=topo.datafile_id).confirmed_at
    broker.clear()

    assert Topography.objects.get(pk=topo.pk).datafile.exists()

    assert Manifest.objects.get(pk=topo.datafile_id).confirmed_at == confirmed_at
    assert len(broker) == 1
    assert Topography.objects.get(pk=topo.pk).task_state == TaskStateModel.PENDING


@pytest.mark.django_db(transaction=True)
def test_a_read_of_a_processed_measurement_changes_nothing(broker):
    topo = Topography1DFactory()
    before = Manifest.objects.get(pk=topo.datafile_id)
    broker.clear()

    assert topo.datafile.exists()
    assert topo.thumbnail.exists()

    assert broker == []
    after = Manifest.objects.get(pk=topo.datafile_id)
    assert after.confirmed_at == before.confirmed_at
    assert Topography.objects.get(pk=topo.pk).task_state == TaskStateModel.SUCCESS


@pytest.mark.django_db(transaction=True)
def test_an_upload_that_has_not_arrived_is_neither_confirmed_nor_processed(broker):
    topo = _unprocessed_measurement(uploaded=False)
    broker.clear()

    assert not topo.datafile.exists()
    assert confirm_and_dispatch(topo.datafile) is None

    manifest = Manifest.objects.get(pk=topo.datafile_id)
    assert manifest.confirmed_at is None
    assert not manifest.file
    assert broker == []
    assert Topography.objects.get(pk=topo.pk).task_state == TaskStateModel.NOTRUN


@pytest.mark.django_db(transaction=True)
def test_a_receiver_failure_does_not_break_the_read(broker, caplog):
    topo = _unprocessed_measurement()
    manifest = Manifest.objects.get(pk=topo.datafile_id)

    with mock.patch(
        "topobank.manager.signals.dispatch_processing",
        side_effect=RuntimeError("lock wait timeout"),
    ):
        with transaction.atomic():
            assert manifest.exists()
            # The transaction the reader is in is still usable
            assert Topography.objects.filter(pk=topo.pk).exists()

    assert "lock wait timeout" in caplog.text
    assert Manifest.objects.get(pk=topo.datafile_id).confirmed_at is not None
    assert manifest.read()  # and so is the file


@pytest.mark.django_db(transaction=True)
def test_an_instance_notifies_once(broker):
    topo = _unprocessed_measurement()
    manifest = Manifest.objects.get(pk=topo.datafile_id)

    with mock.patch(
        "topobank.manager.signals.dispatch_processing"
    ) as dispatch_processing:
        assert manifest.exists()
        assert manifest.exists()
        assert manifest.read()
        # Another instance of the same manifest notifies again
        assert Manifest.objects.get(pk=topo.datafile_id).exists()

    assert dispatch_processing.call_count == 2


@pytest.mark.django_db(transaction=True)
def test_confirming_takes_one_storage_round_trip(broker):
    topo = _unprocessed_measurement()
    manifest = Manifest.objects.get(pk=topo.datafile_id)

    with mock.patch.object(
        default_storage, "size", wraps=default_storage.size
    ) as size, mock.patch.object(
        default_storage, "exists", wraps=default_storage.exists
    ) as exists:
        assert manifest.confirm_upload()

    assert size.call_count == 1
    exists.assert_not_called()
    assert manifest.size_bytes == manifest.file.size > 0


@pytest.mark.django_db(transaction=True)
def test_storage_trouble_leaves_the_upload_unconfirmed(broker, caplog):
    topo = _unprocessed_measurement()
    manifest = Manifest.objects.get(pk=topo.datafile_id)

    with mock.patch.object(default_storage, "size", side_effect=OSError("slow down")):
        assert not manifest.exists()

    assert "slow down" in caplog.text
    assert Manifest.objects.get(pk=topo.datafile_id).confirmed_at is None
    assert broker == []
    # Once storage answers again, the upload is confirmed after all
    assert manifest.exists()
    assert len(broker) == 1


@pytest.mark.django_db(transaction=True)
def test_a_copy_whose_file_never_arrived_is_confirmed_once_it_does(broker):
    topo = Topography1DFactory()
    original = topo.datafile

    with mock.patch.object(Manifest, "save_file", side_effect=OSError("storage")):
        with pytest.raises(OSError):
            original.deepcopy()
    copy = Manifest.objects.exclude(pk=original.pk).latest("pk")
    assert copy.confirmed_at is None
    assert not copy.file
    assert not copy.exists()

    # The object turns up at the copy's storage path after all
    with original.file.open("rb") as fobj:
        default_storage.save(copy.generate_storage_path(), File(fobj))

    assert copy.exists()
    stored = Manifest.objects.get(pk=copy.pk)
    assert stored.file
    assert stored.confirmed_at is not None
    assert stored.size_bytes == original.file.size


@pytest.mark.django_db(transaction=True)
def test_a_confirmed_manifest_that_lost_its_file_is_confirmed_again(broker):
    """`confirmed_at` set but no file: a replacement that failed halfway."""
    topo = Topography1DFactory()
    manifest = Manifest.objects.get(pk=topo.datafile_id)
    confirmed_at = manifest.confirmed_at
    path = manifest.file.name
    Manifest.objects.filter(pk=manifest.pk).update(file=None)
    manifest.refresh_from_db()

    assert manifest.exists()

    stored = Manifest.objects.get(pk=manifest.pk)
    assert stored.file.name == path
    assert stored.confirmed_at == confirmed_at


@pytest.mark.django_db(transaction=True)
def test_a_failed_replacement_leaves_no_reference_to_the_deleted_file(broker):
    topo = Topography1DFactory()
    manifest = Manifest.objects.get(pk=topo.datafile_id)

    with mock.patch.object(
        type(manifest.file), "save", side_effect=OSError("storage unavailable")
    ):
        with pytest.raises(OSError):
            manifest.save_file(ContentFile(b"new contents"))

    stored = Manifest.objects.get(pk=manifest.pk)
    assert not stored.file
    assert not stored.exists()
    with pytest.raises(OSError):
        stored.read()


@pytest.mark.django_db
def test_the_data_files_of_older_zip_imports_are_marked_raw():
    from django.apps import apps

    from importlib import import_module

    migration = import_module(
        "topobank.manager.migrations.0086_backfill_datafile_kind"
    )

    topo = Topography1DFactory()
    Manifest.objects.filter(pk=topo.datafile_id).update(kind="N/A")
    other = Manifest.objects.create(
        permissions=topo.permissions, filename="unrelated.txt", kind="N/A"
    )

    migration.mark_datafiles_raw(apps, None)

    assert Manifest.objects.get(pk=topo.datafile_id).kind == "raw"
    assert Manifest.objects.get(pk=other.pk).kind == "N/A"


@pytest.mark.django_db
def test_a_file_stored_by_the_application_is_confirmed():
    """Zip imports and copies store the file themselves (`save_file`)."""
    topo = Topography1DFactory()
    manifest = Manifest.objects.create(
        permissions=topo.permissions, filename="stored.txt", kind="raw"
    )
    assert manifest.confirmed_at is None

    # Storage has no object for the manifest yet
    with mock.patch.object(default_storage, "size", side_effect=FileNotFoundError) as size:
        manifest.save_file(ContentFile(b"0 1\n1 2\n"))

    stored = Manifest.objects.get(pk=manifest.pk)
    assert stored.confirmed_at is not None
    assert stored.size_bytes == 8
    assert stored.file.read() == b"0 1\n1 2\n"
    # Storage was asked once whether an object was there, and not again for
    # the size: that came from the content
    assert size.call_count == 1


@pytest.mark.django_db
def test_zip_imported_measurements_are_confirmed(broker):
    user = UserFactory()
    surface = SurfaceFactory(created_by=user)
    Topography1DFactory(surface=surface)
    Topography1DFactory(surface=surface)

    outfile = tempfile.NamedTemporaryFile(mode="wb", delete=False)
    export_container_zip(outfile, [surface])
    outfile.close()
    try:
        with zipfile.ZipFile(outfile.name, mode="r") as zf:
            (imported,) = import_container_zip(zf, UserFactory())
    finally:
        os.remove(outfile.name)

    measurements = list(imported.topography_set.all())
    assert len(measurements) == 2
    for topo in measurements:
        assert topo.datafile.kind == "raw"
        assert topo.datafile.confirmed_at is not None
        assert topo.datafile.size_bytes == topo.datafile.file.size > 0
        # Processing them is the importer's call
        assert topo.task_state == TaskStateModel.NOTRUN
