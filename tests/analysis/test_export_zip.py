"""
Tests for bundling workflow results into a ZIP archive
(``topobank.analysis.export_zip`` and ``topobank.analysis.zip_model``).
"""

import datetime
import io
import zipfile

import pytest
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

from topobank.analysis.custodian import periodic_cleanup
from topobank.analysis.export_zip import (
    EXCLUDED_DIRECTORIES,
    export_results_zip,
    result_info_text,
)
from topobank.analysis.models import WorkflowResult
from topobank.analysis.zip_model import ResultZipContainer
from topobank.files.models import Manifest
from topobank.testing.factories import (
    FailedTopographyAnalysisFactory,
    PermissionSetFactory,
    TopographyAnalysisFactory,
)


def _archive(results):
    """Bundle `results` and return the resulting archive, opened for reading."""
    data = io.BytesIO()
    export_results_zip(data, results)
    data.seek(0)
    return zipfile.ZipFile(data, mode="r")


@pytest.mark.django_db
def test_archive_contains_result_files_and_metadata():
    analysis = TopographyAnalysisFactory()
    directory = analysis.subject.name.lower()

    with _archive([analysis]) as zip_file:
        names = zip_file.namelist()
        # The files written by the testing workflow are all present ...
        for filename in ["result.json", "series-0.json", "series-1.json", "test.txt"]:
            assert f"{directory}/{filename}" in names
        # ... and so are the descriptions
        assert f"{directory}/info.txt" in names
        assert "README.txt" in names

        # Files are readable and carry the original content
        assert zip_file.read(f"{directory}/test.txt") == b"Test!!!"


@pytest.mark.django_db
def test_archive_directory_is_named_after_the_subject():
    analysis = TopographyAnalysisFactory()
    with _archive([analysis]) as zip_file:
        directories = {name.split("/")[0] for name in zip_file.namelist()}
        directories.discard("README.txt")
        assert directories == {analysis.subject.name.lower()}


@pytest.mark.django_db
def test_archive_disambiguates_subjects_with_the_same_name():
    first = TopographyAnalysisFactory()
    # Measurement names are unique only within a dataset, so two results can
    # well have equally named subjects.
    second = TopographyAnalysisFactory(subject_topography__name=first.subject.name)
    assert first.subject.name == second.subject.name
    assert first.subject.surface != second.subject.surface

    with _archive([first, second]) as zip_file:
        names = zip_file.namelist()
        # Both results are present under distinct directories, so neither
        # overwrites the other
        assert f"{first.subject.name.lower()}-{first.id}/result.json" in names
        assert f"{second.subject.name.lower()}-{second.id}/result.json" in names


@pytest.mark.django_db
def test_archive_skips_display_only_artifacts():
    analysis = TopographyAnalysisFactory()
    # Deep-zoom tiles are a rendering of data that is archived anyway; they must
    # not be bundled, or an archive would grow by thousands of small files.
    analysis.folder.save_file(
        f"step-0/{EXCLUDED_DIRECTORIES[0]}/pressure/0/0_0.png", "der", ContentFile(b"x")
    )
    analysis.folder.save_file("step-0/nc/results.nc", "der", ContentFile(b"y"))

    with _archive([analysis]) as zip_file:
        names = zip_file.namelist()
        assert not any(f"/{EXCLUDED_DIRECTORIES[0]}/" in name for name in names)
        # Data files below the same step are kept
        assert any(name.endswith("step-0/nc/results.nc") for name in names)


@pytest.mark.django_db
def test_archive_reports_unreadable_files_in_place(mocker):
    analysis = TopographyAnalysisFactory()
    mocker.patch(
        "topobank.files.models.Manifest.open", side_effect=OSError("file is gone")
    )

    with _archive([analysis]) as zip_file:
        names = zip_file.namelist()
        # The archive is still built, with an error note instead of the file
        assert any(name.endswith("-error.txt") for name in names)
        error = zip_file.read(
            [name for name in names if name.endswith("-error.txt")][0]
        ).decode()
        assert "file is gone" in error


@pytest.mark.django_db
def test_info_text_describes_the_analysis():
    analysis = TopographyAnalysisFactory()
    info = result_info_text(analysis)
    assert analysis.subject.name in info
    assert "Start time of analysis task" in info
    assert str(analysis.kwargs) in info


@pytest.mark.django_db
def test_info_text_asks_for_citation_of_dois():
    analysis = TopographyAnalysisFactory(dois=["10.1000/xyz"])
    info = result_info_text(analysis)
    assert "PLEASE CITE" in info
    assert "10.1000/xyz" in info


@pytest.mark.django_db
def test_info_text_without_configuration():
    analysis = TopographyAnalysisFactory(configuration=None)
    assert "Please recalculate" in result_info_text(analysis)


@pytest.mark.django_db
def test_readme_includes_workflow_specific_documentation(mocker):
    analysis = TopographyAnalysisFactory()
    implementation = analysis.implementation
    mocker.patch.object(
        implementation.Meta, "download_readme", "Contents of a test result", create=True
    )

    with _archive([analysis]) as zip_file:
        assert "Contents of a test result" in zip_file.read("README.txt").decode()


class RecordingProgressRecorder:
    """Captures what a task reports, standing in for the Celery-backed recorder."""

    def __init__(self):
        self.calls = []

    def set_progress(self, current, total, message=None):
        self.calls.append((current, total, message))


@pytest.mark.django_db
def test_bundling_reports_progress():
    analysis = TopographyAnalysisFactory()
    nb_files = analysis.folder.get_valid_files().count()
    assert nb_files > 0

    recorder = RecordingProgressRecorder()
    export_results_zip(io.BytesIO(), [analysis], progress_recorder=recorder)

    # One step per file plus a final one for the README
    assert [current for current, _, _ in recorder.calls] == list(range(nb_files + 2))
    assert all(total == nb_files + 1 for _, total, _ in recorder.calls)
    # Progress starts at zero and ends complete, so a client can show a real bar
    assert recorder.calls[0][0] == 0
    assert recorder.calls[-1][0] == recorder.calls[-1][1]
    # The messages name what is being worked on
    assert any(analysis.subject.name in (message or "") for _, _, message in recorder.calls)


@pytest.mark.django_db
def test_progress_counts_only_the_files_that_are_bundled():
    """Skipped files must not count towards progress.

    A contact mechanics result folder is dominated by deep-zoom tiles (thousands
    of them against a handful of data files). Counting those would drive the bar
    to ~99% instantly and then leave it there for the whole real work.
    """
    analysis = TopographyAnalysisFactory()
    nb_files = analysis.folder.get_valid_files().count()
    for i in range(50):
        analysis.folder.save_file(
            f"step-0/{EXCLUDED_DIRECTORIES[0]}/pressure/0/0_{i}.png",
            "der",
            ContentFile(b"tile"),
        )
    assert analysis.folder.get_valid_files().count() == nb_files + 50

    recorder = RecordingProgressRecorder()
    export_results_zip(io.BytesIO(), [analysis], progress_recorder=recorder)

    # The 50 tiles are neither counted nor stepped over
    assert all(total == nb_files + 1 for _, total, _ in recorder.calls)
    assert recorder.calls[-1][0] == nb_files + 1


@pytest.mark.django_db
def test_bundling_without_a_progress_recorder_still_works():
    analysis = TopographyAnalysisFactory()
    with _archive([analysis]) as zip_file:
        assert "README.txt" in zip_file.namelist()


@pytest.mark.django_db
def test_task_worker_passes_the_progress_recorder_through():
    """`run_task` injects a recorder; it has to reach the exporter."""
    analysis = TopographyAnalysisFactory()
    container = _container(analysis.permissions.user_permissions.first().user)

    recorder = RecordingProgressRecorder()
    container.task_worker(result_ids=[analysis.id], progress_recorder=recorder)

    assert len(recorder.calls) > 0


#
# The container model, which drives the bundling from a Celery task
#


def _container(user):
    return ResultZipContainer.objects.create(
        permissions=PermissionSetFactory(user=user, allow="view")
    )


@pytest.mark.django_db
def test_container_stores_the_archive():
    analysis = TopographyAnalysisFactory()
    container = _container(analysis.permissions.user_permissions.first().user)

    container.task_worker(result_ids=[analysis.id])

    assert container.manifest is not None
    assert container.manifest.filename.endswith(".zip")
    with zipfile.ZipFile(io.BytesIO(container.manifest.read()), mode="r") as zip_file:
        assert f"{analysis.subject.name.lower()}/result.json" in zip_file.namelist()


@pytest.mark.django_db
def test_container_refuses_results_the_user_cannot_see(two_users):
    (user1, user2), (surface1, surface2, surface3) = two_users
    analysis = TopographyAnalysisFactory(subject_topography__surface=surface1)
    container = _container(user2)

    with pytest.raises(PermissionDenied):
        container.task_worker(result_ids=[analysis.id])


@pytest.mark.django_db
def test_container_skips_results_without_data():
    failed = FailedTopographyAnalysisFactory(task_state=WorkflowResult.FAILURE)
    successful = TopographyAnalysisFactory(
        subject_topography__surface=failed.subject.surface
    )
    container = _container(successful.permissions.user_permissions.first().user)

    container.task_worker(result_ids=[failed.id, successful.id])

    with zipfile.ZipFile(io.BytesIO(container.manifest.read()), mode="r") as zip_file:
        directories = {name.split("/")[0] for name in zip_file.namelist()}
        directories.discard("README.txt")
        assert directories == {successful.subject.name.lower()}


@pytest.mark.django_db
def test_container_fails_if_nothing_can_be_bundled():
    failed = FailedTopographyAnalysisFactory(task_state=WorkflowResult.FAILURE)
    container = _container(failed.permissions.user_permissions.first().user)

    with pytest.raises(RuntimeError):
        container.task_worker(result_ids=[failed.id])


@pytest.mark.django_db
def test_custodian_removes_expired_containers():
    analysis = TopographyAnalysisFactory()
    user = analysis.permissions.user_permissions.first().user
    expired = _container(user)
    fresh = _container(user)

    _expire(expired)

    periodic_cleanup()

    assert not ResultZipContainer.objects.filter(pk=expired.pk).exists()
    assert ResultZipContainer.objects.filter(pk=fresh.pk).exists()


def _expire(container):
    """Backdate a container past the grace period for temporary artifacts."""
    ResultZipContainer.objects.filter(pk=container.pk).update(
        updated_at=timezone.now()
        - settings.TOPOBANK_TEMPORARY_DELAY
        - datetime.timedelta(days=1)
    )


@pytest.mark.django_db
def test_custodian_also_removes_the_archive_of_an_expired_container():
    """Expiring a container must not leave its archive behind.

    The `manifest` foreign key is SET_NULL, so nothing would ever collect the
    archive (nor the file in the object store) if deleting the container did not
    take the manifest with it.
    """
    analysis = TopographyAnalysisFactory()
    container = _container(analysis.permissions.user_permissions.first().user)
    container.task_worker(result_ids=[analysis.id])

    manifest_id = container.manifest.id
    storage_path = container.manifest.file.name
    assert default_storage.exists(storage_path)

    _expire(container)
    periodic_cleanup()

    assert not Manifest.objects.filter(pk=manifest_id).exists()
    assert not default_storage.exists(storage_path)


@pytest.mark.django_db
def test_deleting_a_container_directly_also_removes_the_archive():
    """The same has to hold for a single delete, e.g. from the admin."""
    analysis = TopographyAnalysisFactory()
    container = _container(analysis.permissions.user_permissions.first().user)
    container.task_worker(result_ids=[analysis.id])

    manifest_id = container.manifest.id
    storage_path = container.manifest.file.name

    container.delete()

    assert not Manifest.objects.filter(pk=manifest_id).exists()
    assert not default_storage.exists(storage_path)


@pytest.mark.django_db
def test_deleting_a_container_without_an_archive_is_harmless():
    """A container whose task never ran has no manifest to collect."""
    analysis = TopographyAnalysisFactory()
    container = _container(analysis.permissions.user_permissions.first().user)
    assert container.manifest is None

    container.delete()

    assert not ResultZipContainer.objects.filter(pk=container.pk).exists()
