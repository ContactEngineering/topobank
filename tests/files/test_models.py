import pytest
from django.db import IntegrityError

from topobank.authorization import get_permission_model
from topobank.files.models import Manifest, ManifestSet
from topobank.files.utils import file_storage_path
from topobank.testing.factories import ManifestFactory


def test_direct_file_delete(user_alice, mocker):
    m = mocker.patch("django.db.models.fields.files.FieldFile.delete")
    permissions = get_permission_model().objects.create()
    folder = ManifestSet.objects.create(permissions=permissions)
    file = Manifest.objects.create(
        permissions=permissions, folder=folder, created_by=user_alice
    )
    file.delete()
    assert m.call_count == 1


def test_file_delete_via_folder(user_alice, mocker):
    m = mocker.patch("django.db.models.fields.files.FieldFile.delete")
    permissions = get_permission_model().objects.create()
    folder = ManifestSet.objects.create(permissions=permissions)
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
    manifest = ManifestFactory(permissions=get_permission_model().objects.create())
    assert manifest.exists()
    assert manifest.file.name == file_storage_path(manifest, manifest.filename)
    assert get_permission_model().objects.count() == 1

    manifest2 = manifest.deepcopy()
    assert get_permission_model().objects.count() == 1
    assert manifest2.exists()
    assert manifest2.file.name == file_storage_path(manifest2, manifest2.filename)

    manifest.delete()
    assert get_permission_model().objects.count() == 1
    assert manifest2.exists()

    manifest3 = manifest2.deepcopy(manifest2.permissions)
    assert get_permission_model().objects.count() == 1
    assert manifest3.exists()


# -----------------------------------------------------------------------------
# Tests for ManifestSet uniqueness constraint
# -----------------------------------------------------------------------------


@pytest.mark.django_db
class TestManifestSetUniqueness:
    """Tests that ManifestSet enforces unique filenames."""

    def test_unique_constraint_enforced_without_storage_prefix(self, user_alice):
        """Direct creation of duplicate filename should raise IntegrityError."""
        permissions = get_permission_model().objects.create()
        folder = ManifestSet.objects.create(permissions=permissions)
        assert folder.storage_prefix is None  # No storage prefix

        # Create first manifest
        Manifest.objects.create(
            permissions=permissions,
            folder=folder,
            filename="test.json",
            created_by=user_alice,
        )

        # Attempt to create duplicate should raise IntegrityError
        with pytest.raises(IntegrityError):
            Manifest.objects.create(
                permissions=permissions,
                folder=folder,
                filename="test.json",
                created_by=user_alice,
            )

    def test_unique_constraint_enforced_with_storage_prefix(self, user_alice):
        """Direct creation of duplicate filename should raise IntegrityError (with prefix)."""
        permissions = get_permission_model().objects.create()
        folder = ManifestSet.objects.create(
            permissions=permissions,
            storage_prefix="data-lake/results/test/abc123",
        )
        assert folder.storage_prefix is not None

        # Create first manifest
        Manifest.objects.create(
            permissions=permissions,
            folder=folder,
            filename="test.json",
            created_by=user_alice,
        )

        # Attempt to create duplicate should raise IntegrityError
        with pytest.raises(IntegrityError):
            Manifest.objects.create(
                permissions=permissions,
                folder=folder,
                filename="test.json",
                created_by=user_alice,
            )

    def test_same_filename_different_folders_allowed(self, user_alice):
        """Same filename in different ManifestSets should be allowed."""
        permissions = get_permission_model().objects.create()
        folder1 = ManifestSet.objects.create(permissions=permissions)
        folder2 = ManifestSet.objects.create(permissions=permissions)

        # Create manifest with same name in both folders - should succeed
        m1 = Manifest.objects.create(
            permissions=permissions,
            folder=folder1,
            filename="test.json",
            created_by=user_alice,
        )
        m2 = Manifest.objects.create(
            permissions=permissions,
            folder=folder2,
            filename="test.json",
            created_by=user_alice,
        )

        assert m1.filename == m2.filename
        assert m1.folder != m2.folder

    def test_save_file_overwrites_existing(self, user_alice):
        """ManifestSet.save_file should overwrite existing file, not create duplicate."""
        from django.core.files.base import ContentFile

        permissions = get_permission_model().objects.create()
        folder = ManifestSet.objects.create(permissions=permissions)

        # Save first version
        folder.save_file("test.json", "der", ContentFile(b'{"version": 1}'))
        assert folder.files.count() == 1
        m1 = folder.files.get(filename="test.json")
        m1_id = m1.id

        # Save second version with same name - should overwrite
        folder.save_file("test.json", "der", ContentFile(b'{"version": 2}'))
        assert folder.files.count() == 1  # Still only one file
        m2 = folder.files.get(filename="test.json")
        assert m2.id == m1_id  # Same manifest, updated

    def test_save_file_overwrites_with_storage_prefix(self, user_alice):
        """ManifestSet.save_file should overwrite existing file (with prefix)."""
        from django.core.files.base import ContentFile

        permissions = get_permission_model().objects.create()
        folder = ManifestSet.objects.create(
            permissions=permissions,
            storage_prefix="data-lake/results/test/def456",
        )

        # Save first version
        folder.save_file("model.nc", "der", ContentFile(b'netcdf data v1'))
        assert folder.files.count() == 1

        # Save second version with same name - should overwrite
        folder.save_file("model.nc", "der", ContentFile(b'netcdf data v2'))
        assert folder.files.count() == 1  # Still only one file

    def test_save_json_overwrites_existing(self):
        """ManifestSet.save_json should overwrite existing file."""
        permissions = get_permission_model().objects.create()
        folder = ManifestSet.objects.create(permissions=permissions)

        # Save first version
        folder.save_json("result.json", {"version": 1})
        assert folder.files.count() == 1

        # Save second version - should overwrite
        folder.save_json("result.json", {"version": 2})
        assert folder.files.count() == 1

        # Verify content was updated
        data = folder.read_json("result.json")
        assert data["version"] == 2

    def test_different_filenames_same_folder_allowed(self, user_alice):
        """Different filenames in same ManifestSet should be allowed."""
        permissions = get_permission_model().objects.create()
        folder = ManifestSet.objects.create(permissions=permissions)

        Manifest.objects.create(
            permissions=permissions,
            folder=folder,
            filename="file1.json",
            created_by=user_alice,
        )
        Manifest.objects.create(
            permissions=permissions,
            folder=folder,
            filename="file2.json",
            created_by=user_alice,
        )

        assert folder.files.count() == 2
