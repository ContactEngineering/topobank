"""Tests for how `refresh_cache` replaces derived files and saves its results.

Reprocessing creates the new squeezed file, thumbnail and deep zoom images first,
saves the new references, and deletes the old files only once that save has been
committed. It writes only the fields it changed, and nothing at all once a newer
dispatch has taken the measurement over.
"""

import json
import threading
import uuid
from unittest import mock

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import JSONField

from topobank.files.models import Manifest, ManifestSet
from topobank.manager.models import DerivedFileSwap, Topography
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


def _derived_ids(topo):
    return topo.thumbnail_id, topo.deepzoom_id, topo.squeezed_datafile_id


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
def test_superseded_refresh_discards_its_files(broker):
    topo = Topography2DFactory(size_x=1, size_y=1)
    broker.clear()
    old_ids = _derived_ids(topo)
    assert run_task(topo)
    task_id = topo.task_id
    created = []
    real_make_squeezed = Topography.make_squeezed

    def make_squeezed_then_get_superseded(self, *args, **kwargs):
        real_make_squeezed(self, *args, **kwargs)
        created.extend(_derived_ids(self))
        assert run_task(Topography.objects.get(pk=self.pk), force=True)

    ct = ContentType.objects.get_for_model(Topography)
    with mock.patch.object(
        Topography, "make_squeezed", make_squeezed_then_get_superseded
    ):
        task_dispatch.apply(args=[ct.id, topo.pk], task_id=str(task_id)).get()

    stored = Topography.objects.get(pk=topo.pk)
    # The references and files of the previous processing are untouched...
    assert _derived_ids(stored) == old_ids
    assert Manifest.objects.filter(pk=old_ids[0]).exists()
    assert ManifestSet.objects.filter(pk=old_ids[1]).exists()
    assert Manifest.objects.filter(pk=old_ids[2]).exists()
    # ...the ones the superseded run created are gone...
    assert not Manifest.objects.filter(pk__in=[created[0], created[2]]).exists()
    assert not ManifestSet.objects.filter(pk=created[1]).exists()
    # ...and the successor's claim stands
    assert stored.task_state == TaskStateModel.PENDING
    assert stored.task_id != task_id


@pytest.mark.django_db(transaction=True)
def test_failed_refresh_keeps_the_previous_derived_files(broker):
    topo = Topography2DFactory(size_x=1, size_y=1)
    old_ids = _derived_ids(topo)
    created = []
    real_make_deepzoom = Topography.make_deepzoom

    def make_deepzoom_then_fail(self, *args, **kwargs):
        real_make_deepzoom(self, *args, **kwargs)
        created.extend(_derived_ids(self)[:2])
        raise RuntimeError("worker lost")

    with mock.patch.object(Topography, "make_deepzoom", make_deepzoom_then_fail):
        with pytest.raises(RuntimeError):
            topo.refresh_cache()

    assert _derived_ids(topo) == old_ids
    assert _derived_ids(Topography.objects.get(pk=topo.pk)) == old_ids
    assert Manifest.objects.filter(pk=old_ids[0]).exists()
    assert ManifestSet.objects.filter(pk=old_ids[1]).exists()
    assert not Manifest.objects.filter(pk=created[0]).exists()
    assert not ManifestSet.objects.filter(pk=created[1]).exists()


@pytest.mark.django_db(transaction=True)
def test_edits_made_during_processing_survive(broker):
    topo = Topography1DFactory()
    Topography.objects.filter(pk=topo.pk).update(data_source=None, resolution_x=None)
    topo.refresh_from_db()
    real_make_thumbnail = Topography.make_thumbnail

    def make_thumbnail_while_user_edits(self, *args, **kwargs):
        Topography.objects.filter(pk=self.pk).update(
            name="renamed meanwhile", description="edited meanwhile"
        )
        real_make_thumbnail(self, *args, **kwargs)

    with mock.patch.object(
        Topography, "make_thumbnail", make_thumbnail_while_user_edits
    ):
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
    assert not _is_missing_file_error(ValueError())


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

    with mock.patch.object(
        Topography, "_refresh_cached_properties", side_effect=ValueError("the real one")
    ), mock.patch.object(
        Topography, "_save_refreshed", side_effect=RuntimeError("cleanup")
    ):
        with pytest.raises(ValueError, match="the real one"):
            topo.refresh_cache()


def _record_created(created):
    """Patch `DerivedFileSwap.replace` to record the files a refresh creates."""
    real_replace = DerivedFileSwap.replace

    def replace(self, old, new):
        if new is not None:
            created.append(new)
        return real_replace(self, old, new)

    return mock.patch.object(DerivedFileSwap, "replace", replace)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("step", ["_make_deepzoom", "_make_squeezed"])
def test_running_out_of_time_fails_the_refresh_and_deletes_its_files(broker, step):
    """The soft time limit is no problem with the file being generated: it is not
    caught like one, and the files the refresh created so far are deleted rather
    than left behind unreferenced."""
    from celery.exceptions import SoftTimeLimitExceeded

    topo = Topography2DFactory(size_x=1, size_y=1)
    old_ids = _derived_ids(topo)
    created = []

    with _record_created(created), mock.patch.object(
        Topography, step, side_effect=SoftTimeLimitExceeded()
    ):
        with pytest.raises(SoftTimeLimitExceeded):
            topo.refresh_cache()

    assert created
    for obj in created:
        assert not type(obj)._base_manager.filter(pk=obj.pk).exists()
    assert _derived_ids(Topography.objects.get(pk=topo.pk)) == old_ids
    assert Manifest.objects.filter(pk__in=[old_ids[0], old_ids[2]]).count() == 2
    assert ManifestSet.objects.filter(pk=old_ids[1]).exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "target, model",
    [
        ("topobank.files.models.Manifest.save_file", Manifest),
        ("topobank.manager.models.render_deepzoom", ManifestSet),
    ],
)
def test_running_out_of_time_inside_a_step_deletes_the_file_it_was_making(
    broker, target, model
):
    from celery.exceptions import SoftTimeLimitExceeded

    topo = Topography2DFactory(size_x=1, size_y=1)
    old_ids = _derived_ids(topo)
    count = model.objects.count()

    with mock.patch(target, side_effect=SoftTimeLimitExceeded()):
        with pytest.raises(SoftTimeLimitExceeded):
            topo.refresh_cache()

    assert model.objects.count() == count
    assert _derived_ids(Topography.objects.get(pk=topo.pk)) == old_ids


@pytest.mark.django_db(transaction=True)
def test_an_inline_refresh_racing_a_run_leaks_no_files(broker):
    topo = Topography1DFactory()
    broker.clear()
    first_ids = _derived_ids(topo)
    assert run_task(topo)
    inline_ids = []
    real_make_squeezed = Topography.make_squeezed

    def make_squeezed_while_an_inline_refresh_lands(self, *args, **kwargs):
        if not inline_ids:
            inline_ids.append(None)  # only once: the inline refresh comes here too
            inline = Topography.objects.get(pk=self.pk)
            inline.refresh_cache()
            inline_ids[:] = [inline.thumbnail_id, inline.squeezed_datafile_id]
        real_make_squeezed(self, *args, **kwargs)

    ct = ContentType.objects.get_for_model(Topography)
    with mock.patch.object(
        Topography, "make_squeezed", make_squeezed_while_an_inline_refresh_lands
    ):
        task_dispatch.apply(args=[ct.id, topo.pk], task_id=str(topo.task_id)).get()

    stored = Topography.objects.get(pk=topo.pk)
    assert stored.task_state == TaskStateModel.SUCCESS
    live = {stored.thumbnail_id, stored.squeezed_datafile_id}
    replaced = {first_ids[0], first_ids[2], *inline_ids} - live
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
def test_a_failed_save_of_the_results_leaks_no_files(broker):
    topo = Topography1DFactory()
    old_ids = _derived_ids(topo)
    created = []
    real_save_refreshed = Topography._save_refreshed

    def record_then_fail(self, before, swap, failed=False):
        if not failed:
            created.extend(swap.created)
            raise RuntimeError("lock wait timeout")
        return real_save_refreshed(self, before, swap, failed=failed)

    with mock.patch.object(Topography, "_save_refreshed", record_then_fail):
        with pytest.raises(RuntimeError, match="lock wait timeout"):
            topo.refresh_cache()

    assert created
    for obj in created:
        assert not type(obj)._base_manager.filter(pk=obj.pk).exists()
    assert _derived_ids(Topography.objects.get(pk=topo.pk)) == old_ids


@pytest.mark.django_db(transaction=True)
def test_a_measurement_deleted_during_an_inline_refresh_leaks_no_files(broker):
    topo = Topography1DFactory()
    created = []
    real_make_squeezed = Topography.make_squeezed

    def make_squeezed_then_get_deleted(self, *args, **kwargs):
        real_make_squeezed(self, *args, **kwargs)
        created.extend(kwargs["swap"].created)
        Topography.objects.filter(pk=self.pk).delete()

    with mock.patch.object(Topography, "make_squeezed", make_squeezed_then_get_deleted):
        topo.refresh_cache()

    assert created
    for obj in created:
        assert not type(obj)._base_manager.filter(pk=obj.pk).exists()
    assert not Topography.objects.filter(pk=topo.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_a_failed_replacement_retires_the_old_file_once(broker, caplog):
    topo = Topography1DFactory()
    old_squeezed = topo.squeezed_datafile_id
    real_create = Manifest.objects.create

    def create_fails_for_the_squeezed_file(**kwargs):
        if kwargs.get("filename", "").endswith("-squeezed.nc"):
            raise OSError("storage unavailable")
        return real_create(**kwargs)

    with mock.patch.object(
        Manifest.objects, "create", side_effect=create_fails_for_the_squeezed_file
    ):
        topo.refresh_cache()

    assert Topography.objects.get(pk=topo.pk).squeezed_datafile_id is None
    assert not Manifest.objects.filter(pk=old_squeezed).exists()
    assert "Could not delete derived file" not in caplog.text
