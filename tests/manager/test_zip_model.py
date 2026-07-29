"""Tests for topobank.manager.zip_model.ZipContainer."""

import json
import zipfile

import pytest
from django.core.exceptions import PermissionDenied

from topobank.manager.zip_model import ZipContainer
from topobank.testing.factories import SurfaceFactory, UserFactory
from topobank.testing.mock_auth.authorization.models import PermissionSet


def _single_user_permissions(allow="full"):
    user = UserFactory()
    permissions = PermissionSet.objects.create()
    permissions.grant(user, allow)
    return user, permissions


def _container_of(container):
    """Open the archive a container has built."""
    return zipfile.ZipFile(container.manifest.file, mode="r")


@pytest.mark.django_db
def test_create_empty_manifest():
    _, permissions = _single_user_permissions()
    container = ZipContainer.objects.create(permissions=permissions)
    assert container.manifest is None

    container.create_empty_manifest()

    assert container.manifest is not None
    assert container.manifest.filename == "container.zip"


@pytest.mark.django_db
def test_create_empty_manifest_twice_raises():
    _, permissions = _single_user_permissions()
    container = ZipContainer.objects.create(permissions=permissions)
    container.create_empty_manifest()

    with pytest.raises(RuntimeError):
        container.create_empty_manifest()


@pytest.mark.django_db
def test_task_worker_nothing_to_do():
    # No manifest and no tag / surface ids -> nothing to do, must not raise.
    _, permissions = _single_user_permissions()
    container = ZipContainer.objects.create(permissions=permissions)
    container.task_worker()


@pytest.mark.django_db
def test_task_worker_requires_single_user():
    user_a, permissions = _single_user_permissions()
    permissions.grant(UserFactory(), "view")  # now two users

    container = ZipContainer.objects.create(permissions=permissions)
    with pytest.raises(PermissionDenied):
        container.task_worker()


@pytest.mark.django_db
def test_export_zip_without_target_raises():
    _, permissions = _single_user_permissions()
    container = ZipContainer.objects.create(permissions=permissions)
    with pytest.raises(RuntimeError):
        container.export_zip()


@pytest.mark.django_db
def test_export_zip_names_the_archive_after_the_dataset():
    """Without `archive_name` the name is still derived from the datasets."""
    user, permissions = _single_user_permissions()
    surface = SurfaceFactory(created_by=user, name="My Nice Surface")

    container = ZipContainer.objects.create(permissions=permissions)
    container.export_zip(surface_ids=[surface.id])

    assert container.manifest.filename == "my-nice-surface.zip"


@pytest.mark.django_db
def test_export_zip_honors_archive_name():
    """Deployments that group datasets differently name the download themselves.

    Two datasets would otherwise collapse to the generic
    'digital-surface-twins.zip', which says nothing about what the user asked
    to download.
    """
    user, permissions = _single_user_permissions()
    surfaces = [
        SurfaceFactory(created_by=user, name="S0"),
        SurfaceFactory(created_by=user, name="S1"),
    ]

    container = ZipContainer.objects.create(permissions=permissions)
    container.export_zip(
        surface_ids=[s.id for s in surfaces], archive_name="Batch 17 / Q3"
    )

    assert container.manifest.filename == "batch-17-q3.zip"


@pytest.mark.django_db
def test_export_zip_falls_back_when_archive_name_has_no_slug():
    """A name that slugifies to nothing must not produce a bare '.zip'."""
    user, permissions = _single_user_permissions()
    surfaces = [
        SurfaceFactory(created_by=user, name="S0"),
        SurfaceFactory(created_by=user, name="S1"),
    ]

    container = ZipContainer.objects.create(permissions=permissions)
    container.export_zip(surface_ids=[s.id for s in surfaces], archive_name="///")

    assert container.manifest.filename == "digital-surface-twins.zip"


@pytest.mark.django_db
def test_export_zip_passes_extra_metadata_through():
    """`extra_metadata` reaches the container metadata unchanged.

    Callers attach grouping information that only they know about (e.g. the SDS
    API's training groups) so that an import can recreate it.
    """
    user, permissions = _single_user_permissions()
    surfaces = [
        SurfaceFactory(created_by=user, name="S0"),
        SurfaceFactory(created_by=user, name="S1"),
    ]
    extra = {"training_groups": [{"name": "Tiles 2024", "members": [0, 1]}]}

    container = ZipContainer.objects.create(permissions=permissions)
    container.export_zip(surface_ids=[s.id for s in surfaces], extra_metadata=extra)

    with _container_of(container) as zf:
        assert json.load(zf.open("index.json"))["extra"] == extra


@pytest.mark.django_db
def test_task_worker_forwards_archive_name_and_extra_metadata():
    """The task entry point must not drop the arguments on the floor."""
    user, permissions = _single_user_permissions()
    surface = SurfaceFactory(created_by=user, name="S0")
    extra = {"training_groups": [{"name": "Tiles 2024", "members": [0]}]}

    container = ZipContainer.objects.create(permissions=permissions)
    container.task_worker(
        surface_ids=[surface.id], archive_name="Folder A", extra_metadata=extra
    )

    assert container.manifest.filename == "folder-a.zip"
    with _container_of(container) as zf:
        assert json.load(zf.open("index.json"))["extra"] == extra


@pytest.mark.django_db
def test_export_zip_spills_large_archives_to_disk(settings):
    """The archive is streamed through a spooled file, not held in memory.

    A multi-GB container built in RAM OOM-kills the worker, and the task is then
    redelivered and OOMs again. Forcing the spool threshold to zero proves the
    rollover path is exercised rather than merely available.
    """
    settings.TOPOBANK_SPOOL_MAX_SIZE = 0

    user, permissions = _single_user_permissions()
    surface = SurfaceFactory(created_by=user, name="S0")

    container = ZipContainer.objects.create(permissions=permissions)
    container.export_zip(surface_ids=[surface.id])

    with _container_of(container) as zf:
        assert "index.json" in zf.namelist()


@pytest.mark.django_db
def test_deleting_a_container_also_removes_the_archive():
    """Deleting a container must not leave its archive behind.

    The `manifest` foreign key is SET_NULL, so nothing would ever collect the
    archive (nor the file in the object store) if deleting the container did not
    take the manifest with it. Containers are transient download bundles that
    the custodian removes in bulk, so a leak here accumulates silently.
    """
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    from topobank.files.models import Manifest

    _, permissions = _single_user_permissions()
    container = ZipContainer.objects.create(permissions=permissions)
    container.create_empty_manifest()
    container.manifest.save_file(ContentFile(b"pretend this is a ZIP archive"))

    manifest_id = container.manifest.id
    storage_path = container.manifest.file.name
    assert default_storage.exists(storage_path)

    container.delete()

    assert not Manifest.objects.filter(pk=manifest_id).exists()
    assert not default_storage.exists(storage_path)


@pytest.mark.django_db
def test_bulk_deleting_containers_also_removes_their_archives():
    """The custodian deletes containers via a queryset, which skips `delete()`."""
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    from topobank.files.models import Manifest

    storage_paths = []
    manifest_ids = []
    for _ in range(2):
        _, permissions = _single_user_permissions()
        container = ZipContainer.objects.create(permissions=permissions)
        container.create_empty_manifest()
        container.manifest.save_file(ContentFile(b"pretend this is a ZIP archive"))
        manifest_ids.append(container.manifest.id)
        storage_paths.append(container.manifest.file.name)

    ZipContainer.objects.all().delete()

    assert not Manifest.objects.filter(pk__in=manifest_ids).exists()
    for storage_path in storage_paths:
        assert not default_storage.exists(storage_path)


@pytest.mark.django_db
def test_manager_container_uses_spooled_temporary_file_with_setting(mocker, settings):
    import tempfile
    settings.TOPOBANK_SPOOL_MAX_SIZE = 456789
    spooled_mock = mocker.patch("tempfile.SpooledTemporaryFile", wraps=tempfile.SpooledTemporaryFile)

    user, permissions = _single_user_permissions()
    surface = SurfaceFactory(created_by=user)

    container = ZipContainer.objects.create(permissions=permissions)
    container.export_zip(surface_ids=[surface.id])

    spooled_mock.assert_called_once_with(max_size=456789)
