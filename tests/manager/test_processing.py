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
from django.core.files.storage import default_storage

from topobank.files.models import Manifest
from topobank.manager import processing
from topobank.manager.models import Topography, processing_storage_prefix
from topobank.taskapp.utils import task_dispatch
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


def test_the_thumbnail_format_has_a_default(settings):
    del settings.TOPOBANK_THUMBNAIL_FORMAT
    topo = Topography(name="measurement", instrument_parameters={})

    assert topo.inspection_parameters().thumbnail_format == "jpeg"


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
def test_a_result_that_went_through_json_applies_like_one_that_did_not(broker):
    """A first inspection, which takes the date and instrument from the file."""
    inline = Topography2DFactory(filename="example3.di")
    other = Topography2DFactory(filename="example3.di")
    Topography.objects.filter(pk__in=[inline.pk, other.pk]).update(
        data_source=None, resolution_x=None, bandwidth_lower=None,
        measurement_date=None, instrument_name="",
    )
    inline.refresh_from_db()
    inline.refresh_cache()
    result, writer = _inspect(Topography.objects.get(pk=other.pk))
    restored = processing.InspectionResult.from_dict(
        json.loads(json.dumps(result.to_dict()))
    )

    assert Topography.objects.get(pk=other.pk).apply_inspection(
        restored, prefix=writer.prefix
    )

    a = Topography.objects.get(pk=inline.pk)
    b = Topography.objects.get(pk=other.pk)
    assert a.measurement_date == datetime.date(2014, 12, 15)
    assert a.instrument_name == "Dimension Icon"
    for name in processing.INSPECTED_FIELDS:
        assert getattr(a, name) == getattr(b, name), name
    assert len(b.deepzoom) == len(a.deepzoom) > 0
    assert b.thumbnail.file.read() == a.thumbnail.file.read()


@pytest.mark.django_db(transaction=True)
def test_a_result_recorded_twice_keeps_its_files(broker):
    topo = Topography1DFactory()
    result, writer = _inspect(Topography.objects.get(pk=topo.pk))
    instance = Topography.objects.get(pk=topo.pk)
    ids = []

    for _ in range(2):
        assert instance.apply_inspection(result, prefix=writer.prefix)
        ids.append(Topography.objects.get(pk=topo.pk).thumbnail_id)

    assert ids[0] == ids[1]
    assert all(default_storage.exists(key) for key in result.written_keys())
