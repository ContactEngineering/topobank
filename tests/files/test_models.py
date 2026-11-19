import pytest
from django.apps import apps

from topobank.files.models import Manifest, ManifestSet
from topobank.files.utils import file_storage_path
from topobank.testing.factories import ManifestFactory

PermissionSet = apps.get_model('authorization', 'PermissionSet')


@pytest.mark.django_db
def test_direct_file_delete(user_alice, mocker):
    m = mocker.patch("django.db.models.fields.files.FieldFile.delete")
    permissions = PermissionSet.objects.create()
    folder = ManifestSet.objects.create(permissions=permissions)
    file = Manifest.objects.create(
        permissions=permissions, created_by=user_alice, folder=folder
    )
    file.delete()
    assert m.call_count == 1


@pytest.mark.django_db
def test_file_delete_via_folder(user_alice, mocker):
    m = mocker.patch("django.db.models.fields.files.FieldFile.delete")
    permissions = PermissionSet.objects.create()
    folder = ManifestSet.objects.create(permissions=permissions)
    Manifest.objects.create(
        permissions=permissions,
        created_by=user_alice,
        filename="file1.txt",
        folder=folder,
    )
    Manifest.objects.create(
        permissions=permissions,
        created_by=user_alice,
        filename="file2.txt",
        folder=folder,
    )
    assert Manifest.objects.count() == 2
    folder.remove_files()
    folder.delete()
    assert Manifest.objects.count() == 0
    assert m.call_count == 2


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_register_stored_files_points_manifests_at_the_given_keys(mocker):
    size = mocker.patch("django.db.models.fields.files.FieldFile.size")
    folder = ManifestSet.objects.create(permissions=PermissionSet.objects.create())

    created = folder.register_stored_files(
        [
            {"filename": "model.nc", "key": "data-lake/workflows/wfr-1/model.nc", "size": 12},
            {"filename": "result.json", "key": "data-lake/workflows/wfr-1/result.json"},
        ],
        prefix="data-lake/workflows/wfr-1",
    )

    assert [m.filename for m in created] == ["model.nc", "result.json"]
    stored = {m.filename: m for m in folder.get_valid_files()}
    assert stored["model.nc"].file.name == "data-lake/workflows/wfr-1/model.nc"
    assert stored["model.nc"].size_bytes == 12
    assert stored["model.nc"].kind == "der"
    assert stored["model.nc"].permissions_id == folder.permissions_id
    assert stored["result.json"].size_bytes is None
    assert all(m.confirmed_at is not None for m in stored.values())
    # The caller vouches for the objects; storage is never asked
    assert size.call_count == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    "key",
    [
        "data-lake/workflows/wfr-2/model.nc",  # another folder
        "../data-lake/workflows/wfr-1/model.nc",
        "/data-lake/workflows/wfr-1/model.nc",
        "data-lake/workflows/wfr-1/../wfr-1/model.nc",
        "data-lake\\workflows\\wfr-1\\model.nc",
        "",
        None,
    ],
)
def test_register_stored_files_refuses_a_key_outside_the_prefix(key):
    folder = ManifestSet.objects.create(permissions=PermissionSet.objects.create())

    with pytest.raises(ValueError, match="not a storage key"):
        folder.register_stored_files(
            [{"filename": "model.nc", "key": key}], prefix="data-lake/workflows/wfr-1"
        )
    assert folder.get_files().count() == 0


@pytest.mark.django_db
def test_an_empty_prefix_admits_no_key():
    folder = ManifestSet.objects.create(permissions=PermissionSet.objects.create())

    with pytest.raises(ValueError, match="not a storage key"):
        folder.register_stored_files([{"filename": "a.txt", "key": "anywhere/a.txt"}], prefix="")
    assert folder.get_files().count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    "filename", ["", ".", "..", "../b.txt", "/b.txt", "a/./b.txt", "a\\b.txt", "x" * 256, None]
)
def test_register_stored_files_refuses_a_filename_that_is_not_a_relative_path(filename):
    folder = ManifestSet.objects.create(permissions=PermissionSet.objects.create())

    with pytest.raises(ValueError, match="not a valid file name"):
        folder.register_stored_files([{"filename": filename, "key": "p/a.txt"}], prefix="p")
    assert folder.get_files().count() == 0


@pytest.mark.parametrize(
    "key, expected",
    [("a/b.txt", True), (".", False), ("a/./b.txt", False), ("./a", False), ("", False)],
)
def test_is_storage_key(key, expected):
    from topobank.files.utils import is_storage_key

    assert is_storage_key(key) is expected


@pytest.mark.django_db
def test_register_stored_files_without_a_prefix_only_checks_the_key_shape():
    folder = ManifestSet.objects.create(permissions=PermissionSet.objects.create())

    folder.register_stored_files([{"filename": "a.txt", "key": "anywhere/a.txt"}])
    with pytest.raises(ValueError):
        folder.register_stored_files([{"filename": "b.txt", "key": "../b.txt"}])

    assert [m.filename for m in folder.get_files()] == ["a.txt"]


@pytest.mark.django_db
def test_register_stored_files_refuses_duplicate_filenames():
    folder = ManifestSet.objects.create(permissions=PermissionSet.objects.create())
    folder.register_stored_files([{"filename": "a.txt", "key": "p/a.txt"}], prefix="p")

    with pytest.raises(FileExistsError, match="a.txt"):
        folder.register_stored_files(
            [{"filename": "a.txt", "key": "p/a2.txt"}, {"filename": "b.txt", "key": "p/b.txt"}],
            prefix="p",
        )
    with pytest.raises(FileExistsError, match="c.txt"):
        folder.register_stored_files(
            [{"filename": "c.txt", "key": "p/c.txt"}, {"filename": "c.txt", "key": "p/c2.txt"}],
            prefix="p",
        )

    # Nothing of a refused batch is written
    assert [m.filename for m in folder.get_files()] == ["a.txt"]
