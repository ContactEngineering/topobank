"""Pluggable processing steps (`topobank.manager.steps`) and the derived folder."""

import json
import os
from unittest import mock

import pytest
from django.core.management import call_command

from topobank.files.models import Manifest, ManifestSet
from topobank.manager import processing, steps
from topobank.manager.models import Topography
from topobank.manager.reprocessing import outdated_topographies
from topobank.testing.factories import Topography1DFactory, Topography2DFactory

MARKER = "tests.manager.test_steps.MarkerStep"


class MarkerStep:
    """A step as a plugin would provide one: for maps only, writing its options."""

    name = "marker"
    version = "3"
    required = False

    def applies_to(self, adapter):
        return adapter.has_deepzoom

    def owns(self, filename):
        return filename.startswith("marker/")

    def write(self, data, adapter, params, options, save):
        path = os.path.join(self.tmpdir, "index.json")
        with open(path, "w") as f:
            json.dump({"options": options, "nb_grid_pts": list(data.nb_grid_pts)}, f)
        save("marker/index.json", path)

    tmpdir = "/tmp"


@pytest.fixture
def marker(settings, tmp_path):
    MarkerStep.tmpdir = str(tmp_path)
    settings.TOPOBANK_PROCESSING_STEPS = ["squeezed", "thumbnail", "deepzoom", MARKER]
    settings.TOPOBANK_PROCESSING_STEP_OPTIONS = {"marker": {"scales": [1, 2]}}
    yield


def _names(topo):
    return sorted(topo.derived.files.values_list("filename", flat=True))


@pytest.mark.django_db
def test_a_configured_step_writes_into_the_derived_folder(marker):
    topo = Topography2DFactory(size_x=1, size_y=1)

    names = _names(topo)
    assert "marker/index.json" in names
    assert {"squeezed.nc", "thumbnail.jpeg", "dzi.json"} <= set(names)
    assert topo.derived.read_json("marker/index.json")["options"] == {"scales": [1, 2]}
    record = topo.processing_steps.get(name="marker")
    assert record.version.startswith("3+") and record.succeeded


@pytest.mark.django_db
def test_a_step_that_does_not_apply_to_the_kind_does_not_run(marker):
    topo = Topography1DFactory()

    assert not any(name.startswith(("marker/", "dzi")) for name in _names(topo))
    assert sorted(topo.processing_steps.values_list("name", flat=True)) == [
        "squeezed",
        "thumbnail",
    ]
    assert topo.deepzoom is None


@pytest.mark.django_db
def test_the_squeezed_file_is_always_written(settings):
    settings.TOPOBANK_PROCESSING_STEPS = ["thumbnail"]
    topo = Topography2DFactory(size_x=1, size_y=1)

    assert _names(topo) == ["squeezed.nc", "thumbnail.jpeg"]
    assert topo.deepzoom is None


@pytest.mark.django_db
def test_a_failed_optional_step_leaves_the_rest_of_the_measurement(marker, caplog):
    with mock.patch.object(MarkerStep, "write", side_effect=RuntimeError("no maps")):
        topo = Topography2DFactory(size_x=1, size_y=1)

    assert not any(name.startswith("marker/") for name in _names(topo))
    assert topo.squeezed_datafile is not None
    record = topo.processing_steps.get(name="marker")
    assert not record.succeeded and record.error == "no maps"
    assert "missing derived files" not in caplog.text


@pytest.mark.django_db
def test_a_step_may_write_only_its_own_files(marker):
    def write(self, data, adapter, params, options, save):
        save("thumbnail.jpeg", __file__)

    with mock.patch.object(MarkerStep, "write", write):
        topo = Topography2DFactory(size_x=1, size_y=1)

    assert not topo.processing_steps.get(name="marker").succeeded
    assert topo.thumbnail.read() != open(__file__, "rb").read()


@pytest.mark.django_db
def test_rerunning_one_step_keeps_the_other_steps_files(
    marker, django_capture_on_commit_callbacks
):
    topo = Topography2DFactory(size_x=1, size_y=1)
    old_folder = topo.derived
    kept = {
        name: key
        for name, key in old_folder.files.values_list("filename", "file")
        if name != "thumbnail.jpeg"
    }
    old_thumbnail = topo.thumbnail.file.name

    with django_capture_on_commit_callbacks(execute=True):
        topo.make_thumbnail()

    topo = Topography.objects.get(pk=topo.pk)
    assert topo.derived != old_folder
    assert not ManifestSet.objects.filter(pk=old_folder.pk).exists()
    now = dict(topo.derived.files.values_list("filename", "file"))
    assert topo.thumbnail.file.name != old_thumbnail
    assert {name: now[name] for name in kept} == kept
    assert topo.deepzoom == topo.derived


@pytest.mark.django_db
def test_a_new_inspection_drops_the_files_of_a_step_no_longer_configured(
    marker, settings
):
    topo = Topography2DFactory(size_x=1, size_y=1)
    assert "marker/index.json" in _names(topo)

    settings.TOPOBANK_PROCESSING_STEPS = ["squeezed", "thumbnail", "deepzoom"]
    topo.refresh_cache()

    topo = Topography.objects.get(pk=topo.pk)
    assert not any(name.startswith("marker/") for name in _names(topo))
    assert not topo.processing_steps.filter(name="marker").exists()


@pytest.mark.django_db
def test_measurements_processed_without_a_new_step_are_out_of_date(settings, marker):
    settings.TOPOBANK_PROCESSING_STEPS = ["squeezed", "thumbnail", "deepzoom"]
    topo_map = Topography2DFactory(size_x=1, size_y=1)
    line_scan = Topography1DFactory()
    assert not outdated_topographies().exists()

    settings.TOPOBANK_PROCESSING_STEPS += [MARKER]
    # The step applies to maps only
    assert list(outdated_topographies()) == [topo_map]

    with mock.patch(
        "topobank.manager.management.commands.reprocess_outdated.run_task",
        side_effect=lambda topo: topo.refresh_cache() or True,
    ):
        call_command("reprocess_outdated")

    assert not outdated_topographies().exists()
    assert "marker/index.json" in _names(Topography.objects.get(pk=topo_map.pk))
    assert line_scan.processing_steps.count() == 2


@pytest.mark.django_db
def test_changed_options_make_a_step_out_of_date(settings, marker):
    topo = Topography2DFactory(size_x=1, size_y=1)
    assert not outdated_topographies().exists()

    settings.TOPOBANK_PROCESSING_STEP_OPTIONS = {"marker": {"scales": [1, 2, 4]}}

    assert list(outdated_topographies()) == [topo]


@pytest.mark.django_db
def test_a_failed_step_is_retried_only_on_request(settings, marker):
    with mock.patch.object(MarkerStep, "write", side_effect=RuntimeError("no maps")):
        topo = Topography2DFactory(size_x=1, size_y=1)

    assert not outdated_topographies().exists()
    assert list(outdated_topographies(retry_failed=True)) == [topo]


@pytest.mark.django_db
def test_a_measurement_without_a_kind_is_out_of_date():
    topo = Topography2DFactory(size_x=1, size_y=1)
    Topography.objects.filter(pk=topo.pk).update(kind=None)

    assert list(outdated_topographies()) == [topo]


def test_steps_are_resolved_by_name_or_import_path():
    resolved = steps.resolve_steps(["thumbnail", MARKER])
    assert [step.name for step in resolved] == ["squeezed", "thumbnail", "marker"]
    with pytest.raises(ImportError):
        steps.resolve_step("no-such-step")


def test_options_are_part_of_the_version():
    step = steps.BUILTIN_STEPS["thumbnail"]
    assert steps.step_version(step) == "1"
    assert steps.step_version(step, {}) == "1"
    assert steps.step_version(step, {"a": 1}) == steps.step_version(step, {"a": 1})
    assert steps.step_version(step, {"a": 1}) != steps.step_version(step, {"a": 2})


def test_the_steps_travel_with_the_parameters():
    params = processing.InspectionParameters(
        name="m",
        filename="m.txt",
        data_source=None,
        size_x=1.0,
        size_y=1.0,
        unit="um",
        height_scale=1.0,
        is_periodic=False,
        fill_undefined_data_mode="do-not-fill",
        detrend_mode="center",
        instrument_name="",
        instrument_parameters={},
        steps=("squeezed", MARKER),
        step_options={"marker": {"scales": [1]}},
    )
    restored = processing.InspectionParameters.from_dict(
        json.loads(json.dumps(params.to_dict()))
    )
    assert restored == params


@pytest.mark.django_db
def test_removing_a_measurement_removes_its_derived_folder():
    topo = Topography2DFactory(size_x=1, size_y=1)
    folder, files = topo.derived_id, list(topo.derived.files.values_list("pk", flat=True))

    topo.remove_files()

    assert not ManifestSet.objects.filter(pk=folder).exists()
    assert not Manifest.objects.filter(pk__in=files).exists()
