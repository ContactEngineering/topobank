"""Tests for confirming an uploaded data file and starting its processing.

An upload is confirmed exactly once, whichever gets to it first: the storage's
notification (`confirm_and_dispatch`), a read of the file (`Manifest.read`,
through `Manifest.confirm_upload`), or both at the same time. Only
`confirm_and_dispatch` starts its processing, also exactly once. The race runs on
real transactions, with one database connection per thread; only the broker is
replaced.
"""

import datetime
import os
import tempfile
import threading
import zipfile
from unittest import mock

import pytest
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import connection
from django.utils import timezone

from topobank.files.models import Manifest
from topobank.manager.custodian import periodic_cleanup
from topobank.manager.export_zip import export_container_zip
from topobank.manager.import_zip import import_container_zip
from topobank.manager.models import Topography
from topobank.manager.uploads import confirm_and_dispatch, sweep_unconfirmed_uploads
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
def test_reading_an_arrived_upload_confirms_it_without_starting_processing(broker):
    topo = _unprocessed_measurement()
    broker.clear()

    assert topo.datafile.read()

    manifest = Manifest.objects.get(pk=topo.datafile_id)
    assert manifest.confirmed_at is not None
    assert manifest.file
    assert manifest.size_bytes == manifest.file.size > 0
    assert broker == []
    assert Topography.objects.get(pk=topo.pk).task_state == TaskStateModel.NOTRUN


@pytest.mark.django_db(transaction=True)
def test_exists_only_checks_the_manifest(broker):
    topo = _unprocessed_measurement()
    manifest = Manifest.objects.get(pk=topo.datafile_id)

    with mock.patch.object(default_storage, "size") as size:
        assert not manifest.exists()

    size.assert_not_called()
    assert Manifest.objects.get(pk=topo.datafile_id).confirmed_at is None
    assert broker == []


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
            return manifest.confirm_upload()
        return confirm_and_dispatch(manifest) is not None

    assert _in_threads(6, read_or_notify) == [True] * 6

    manifest = Manifest.objects.get(pk=topo.datafile_id)
    assert manifest.confirmed_at is not None
    assert len(broker) == 1
    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.PENDING
    assert broker[0][1] == str(stored.task_id)


@pytest.mark.django_db(transaction=True)
def test_a_stranded_measurement_is_processed_once_confirm_and_dispatch_finds_it(
    broker,
):
    # Confirmed earlier, by a read say, without ever being dispatched
    topo = _unprocessed_measurement()
    assert topo.datafile.confirm_upload()
    confirmed_at = Manifest.objects.get(pk=topo.datafile_id).confirmed_at
    broker.clear()

    dispatched = confirm_and_dispatch(Topography.objects.get(pk=topo.pk).datafile)

    assert [t.pk for t in dispatched] == [topo.pk]

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
        assert not manifest.confirm_upload()

    assert "slow down" in caplog.text
    assert Manifest.objects.get(pk=topo.datafile_id).confirmed_at is None
    # Once storage answers again, the upload is confirmed after all
    assert manifest.confirm_upload()
    assert Manifest.objects.get(pk=topo.datafile_id).confirmed_at is not None
    assert broker == []


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

    assert copy.confirm_upload()
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

    assert manifest.confirm_upload()

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


@pytest.mark.django_db(transaction=True)
def test_the_sweep_confirms_and_processes_an_upload_that_arrived_unnoticed(broker):
    arrived = _unprocessed_measurement()
    missing = _unprocessed_measurement(uploaded=False)
    recent = _unprocessed_measurement()
    cutoff = timezone.now()
    Manifest.objects.filter(pk=recent.datafile.pk).update(
        created_at=cutoff + datetime.timedelta(minutes=1)
    )

    confirmed = sweep_unconfirmed_uploads(cutoff)

    assert [m.pk for m in confirmed] == [arrived.datafile.pk]
    stored = Topography.objects.get(pk=arrived.pk)
    assert stored.datafile.confirmed_at is not None
    assert stored.task_state == TaskStateModel.PENDING
    assert [args[1] for args, _ in broker] == [arrived.pk]
    for untouched in (missing, recent):
        stored = Topography.objects.get(pk=untouched.pk)
        assert stored.datafile.confirmed_at is None
        assert stored.task_state == TaskStateModel.NOTRUN


@pytest.mark.django_db(transaction=True)
def test_the_sweep_leaves_a_confirmed_upload_alone(broker):
    topo = _unprocessed_measurement()
    assert confirm_and_dispatch(topo.datafile)
    broker.clear()

    assert sweep_unconfirmed_uploads(timezone.now()) == []
    assert broker == []


@pytest.mark.django_db(transaction=True)
def test_the_custodian_processes_an_unnoticed_upload_and_deletes_the_lost_ones(
    broker,
):
    arrived = _unprocessed_measurement()
    missing = _unprocessed_measurement(uploaded=False)
    old = timezone.now() - datetime.timedelta(days=8)
    Manifest.objects.filter(
        pk__in=[arrived.datafile.pk, missing.datafile.pk]
    ).update(created_at=old)

    periodic_cleanup()

    stored = Topography.objects.get(pk=arrived.pk)
    assert stored.datafile.confirmed_at is not None
    assert stored.task_state == TaskStateModel.PENDING
    # The upload that never arrived is deleted as before, and the measurement
    # is left without a data file
    assert not Manifest.objects.filter(pk=missing.datafile.pk).exists()
    assert Topography.objects.get(pk=missing.pk).datafile is None


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
    # Storage was not asked whether an object was there (the manifest says it
    # has none), nor for the size: that came from the content
    assert size.call_count == 0


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
