from topobank.authorization.models import PermissionSet
from topobank.files.models import Folder, Manifest


def test_direct_file_delete(user_alice, mocker):
    m = mocker.patch("django.db.models.fields.files.FieldFile.delete")
    permissions = PermissionSet.objects.create()
    folder = Folder.objects.create(permissions=permissions)
    file = Manifest.objects.create(
        permissions=permissions, folder=folder, uploaded_by=user_alice
    )
    file.delete()
    assert m.call_count == 1


def test_file_delete_via_folder(user_alice, mocker):
    m = mocker.patch("django.db.models.fields.files.FieldFile.delete")
    permissions = PermissionSet.objects.create()
    folder = Folder.objects.create(permissions=permissions)
    Manifest.objects.create(
        permissions=permissions, folder=folder, uploaded_by=user_alice
    )
    Manifest.objects.create(
        permissions=permissions, folder=folder, uploaded_by=user_alice
    )
    assert Manifest.objects.count() == 2
    folder.delete()
    assert Manifest.objects.count() == 0
    assert m.call_count == 2
