"""
Tests for provisional files in a ``ManifestSet``: reservations, provisional
writes, confirmation and discarding.
"""

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from topobank.files.models import Manifest, ManifestSet
from topobank.testing.factories import UserFactory


def _folder(**kwargs):
    from topobank.authorization import get_permission_model

    permissions = get_permission_model().objects.create()
    permissions.grant_for_user(UserFactory(), "full")
    return ManifestSet.objects.create(permissions=permissions, **kwargs)


@pytest.mark.django_db
def test_save_file_confirms_unless_writes_are_provisional():
    folder = _folder()
    folder.save_file("a.txt", "der", ContentFile(b"a"))
    assert folder.get_valid_files().count() == 1
    assert folder.get_provisional_files().count() == 0

    provisional = _folder(provisional_writes=True)
    provisional.save_file("a.txt", "der", ContentFile(b"a"))
    assert provisional.get_valid_files().count() == 0
    assert provisional.get_provisional_files().count() == 1
    # The file is there and readable by the run itself, just not confirmed
    assert provisional.open_file("a.txt", "rb").read() == b"a"


@pytest.mark.django_db
def test_reserve_creates_a_file_less_provisional_manifest_once():
    folder = _folder(provisional_writes=True)
    reserved = folder.reserve("model.nc")
    assert reserved.folder == folder
    assert reserved.permissions == folder.permissions
    assert reserved.kind == "der"
    assert reserved.confirmed_at is None
    assert not reserved.file
    # Where the file is expected: derived from the reservation itself
    assert reserved.generate_storage_path().endswith(f"/{reserved.id}/model.nc")
    # Reserving again returns the same row
    assert folder.reserve("model.nc") == reserved
    assert folder.files.count() == 1


@pytest.mark.django_db
def test_save_file_fills_a_reservation_in_place():
    folder = _folder(provisional_writes=True)
    reserved = folder.reserve("model.nc")
    folder.save_file("model.nc", "der", ContentFile(b"bytes"))
    manifest = folder.files.get(filename="model.nc")
    assert manifest.pk == reserved.pk
    assert manifest.file
    assert manifest.confirmed_at is None


@pytest.mark.django_db
def test_confirm_all_confirms_written_files_and_drops_unfilled_reservations():
    folder = _folder(provisional_writes=True)
    folder.reserve("model.nc")
    folder.reserve("metadata.json")
    folder.save_file("model.nc", "der", ContentFile(b"bytes"))
    folder.save_file("extra.json", "der", ContentFile(b"{}"))

    assert folder.confirm_all() == 2

    names = set(folder.get_valid_files().values_list("filename", flat=True))
    assert names == {"model.nc", "extra.json"}
    assert folder.get_provisional_files().count() == 0
    assert not Manifest.objects.filter(folder=folder, filename="metadata.json").exists()


@pytest.mark.django_db
def test_discard_provisional_removes_rows_and_storage_objects():
    folder = _folder(provisional_writes=True)
    folder.save_file("confirmed.txt", "der", ContentFile(b"keep"))
    folder.confirm_all()
    folder.reserve("never.nc")
    folder.save_file("partial.txt", "der", ContentFile(b"partial"))
    path = folder.files.get(filename="partial.txt").file.name
    assert default_storage.exists(path)

    assert folder.discard_provisional() == 2

    assert set(folder.files.values_list("filename", flat=True)) == {"confirmed.txt"}
    assert not default_storage.exists(path)


@pytest.mark.django_db
def test_register_files_can_register_provisionally():
    folder = _folder(provisional_writes=True)
    entries = [{"filename": "a.nc", "path": "data-lake/x/a.nc"}]

    folder.register_files(entries, confirm=False)
    manifest = folder.files.get(filename="a.nc")
    assert manifest.confirmed_at is None
    assert manifest.file.name == "data-lake/x/a.nc"

    folder.register_files(entries)  # confirms by default, same row
    manifest.refresh_from_db()
    assert manifest.confirmed_at is not None
    assert folder.files.count() == 1
