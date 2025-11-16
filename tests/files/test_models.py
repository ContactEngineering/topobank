from topobank.authorization.models import PermissionSet
from topobank.files.models import Folder, Manifest
from topobank.files.utils import file_storage_path
from topobank.testing.factories import ManifestFactory


def test_direct_file_delete(user_alice, mocker):
    m = mocker.patch("django.db.models.fields.files.FieldFile.delete")
    permissions = PermissionSet.objects.create()
    folder = Folder.objects.create(permissions=permissions)
    file = Manifest.objects.create(
        permissions=permissions, folder=folder, created_by=user_alice
    )
    file.delete()
    assert m.call_count == 1


def test_file_delete_via_folder(user_alice, mocker):
    m = mocker.patch("django.db.models.fields.files.FieldFile.delete")
    permissions = PermissionSet.objects.create()
    folder = Folder.objects.create(permissions=permissions)
    Manifest.objects.create(
        permissions=permissions,
        folder=folder,
        created_by=user_alice,
        filename="file1.txt",
    )
    Manifest.objects.create(
        permissions=permissions,
        folder=folder,
        created_by=user_alice,
        filename="file2.txt",
    )
    assert Manifest.objects.count() == 2
    folder.delete()
    assert Manifest.objects.count() == 0
    assert m.call_count == 2


def test_deepcopy():
    manifest = ManifestFactory(permissions=PermissionSet.objects.create())
    assert manifest.exists()
    assert manifest.file.name == file_storage_path(manifest, manifest.filename)
    assert PermissionSet.objects.count() == 1

    manifest2 = manifest.deepcopy()
    assert PermissionSet.objects.count() == 1
    assert manifest2.exists()
    assert manifest2.file.name == file_storage_path(manifest2, manifest2.filename)

    manifest.delete()
    assert PermissionSet.objects.count() == 1
    assert manifest2.exists()

    manifest3 = manifest2.deepcopy(manifest2.permissions)
    assert PermissionSet.objects.count() == 1
    assert manifest3.exists()
