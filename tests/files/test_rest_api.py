from pathlib import Path

import pytest
from django.core.files import File
from rest_framework.reverse import reverse

from topobank.authorization.models import PermissionSet, UserPermission
from topobank.files.models import Folder, Manifest
from topobank.files.utils import file_storage_path
from topobank.testing.data import FIXTURE_DATA_DIR
from topobank.testing.utils import upload_file


@pytest.mark.django_db
def test_upload_file(api_client, user_alice, user_bob):
    name = "example3.di"
    input_file_path = Path(f"{FIXTURE_DATA_DIR}/{name}")

    permissions = PermissionSet.objects.create()
    UserPermission.objects.create(parent=permissions, user=user_alice, allow="full")
    folder = Folder.objects.create(permissions=permissions)
    manifest = Manifest.objects.create(
        filename=name,
        permissions=permissions,
        folder=folder,
        uploaded_by=user_alice,
        kind="raw",
    )

    # File belongs to alice, log in as bob
    api_client.force_login(user_bob)

    # Bob should not be able to get upload instructions
    response = api_client.get(
        reverse("files:manifest-api-detail", kwargs={"pk": manifest.id})
    )
    assert response.status_code == 403, response.content

    # Share with bob editable
    manifest.permissions.grant_for_user(user_bob, "edit")

    # Bob should not be able to get upload instructions and upload the file
    response = api_client.get(
        reverse("files:manifest-api-detail", kwargs={"pk": manifest.id})
    )
    assert response.status_code == 200, response.content
    upload_instructions = response.data["upload_instructions"]
    assert upload_instructions is not None

    # Upload file
    upload_file(api_client, upload_instructions, input_file_path)

    # Confirm file upload
    response = api_client.get(
        reverse("files:manifest-api-detail", kwargs={"pk": manifest.id})
    )
    assert response.status_code == 200, response.content
    assert response.data["file"] is not None

    manifest = Manifest.objects.get(id=manifest.id)
    assert manifest.file
    assert manifest.filename == name
    assert manifest.file.name == file_storage_path(manifest, name)


@pytest.mark.django_db
@pytest.mark.parametrize("read_only", [True, False])
def test_delete_file(api_client, user_alice, read_only, handle_usage_statistics):
    permissions = PermissionSet.objects.create()
    UserPermission.objects.create(parent=permissions, user=user_alice, allow="view")
    folder = Folder.objects.create(permissions=permissions, read_only=read_only)
    manifest1 = Manifest.objects.create(
        permissions=permissions,
        folder=folder,
        file=File(open(f"{FIXTURE_DATA_DIR}/dektak-1.csv", "rb")),
    )
    Manifest.objects.create(
        permissions=permissions,
        folder=folder,
        file=File(open(f"{FIXTURE_DATA_DIR}/dummy.txt", "rb")),
    )

    # Try deleting file1 - no permission
    response = api_client.delete(
        reverse("files:manifest-api-detail", kwargs={"pk": manifest1.id})
    )
    assert response.status_code == 403

    # Login user
    api_client.force_login(user_alice)

    # Try deleting file - permission only if folder is not read only
    response = api_client.delete(
        reverse("files:manifest-api-detail", kwargs={"pk": manifest1.id})
    )
    assert response.status_code == 403 if read_only else 200
    assert Manifest.objects.count() == 2 if read_only else 1


@pytest.mark.django_db
@pytest.mark.parametrize("read_only", [True, False])
def test_modify_file(api_client, user_alice, read_only, handle_usage_statistics):
    permissions = PermissionSet.objects.create()
    UserPermission.objects.create(parent=permissions, user=user_alice, allow="view")
    folder = Folder.objects.create(permissions=permissions, read_only=read_only)
    manifest1 = Manifest.objects.create(
        permissions=permissions,
        folder=folder,
        file=File(open(f"{FIXTURE_DATA_DIR}/dektak-1.csv", "rb")),
    )
    Manifest.objects.create(
        permissions=permissions,
        folder=folder,
        file=File(open(f"{FIXTURE_DATA_DIR}/dummy.txt", "rb")),
    )

    old_filename = manifest1.filename
    new_filename = "new_filename.testing"

    # Try patching metadata of file1 - no permission
    response = api_client.patch(
        reverse("files:manifest-api-detail", kwargs={"pk": manifest1.id}),
        {"filename": new_filename},
    )
    assert response.status_code == 403

    # Login user
    api_client.force_login(user_alice)

    # Try deleting file - permission only if folder is not read only
    response = api_client.patch(
        reverse("files:manifest-api-detail", kwargs={"pk": manifest1.id}),
        {"filename": new_filename},
    )
    # 405 is "Method not allowed"
    assert response.status_code == 405 if read_only else 200, response.status_code
    assert (
        Manifest.objects.get(pk=manifest1.pk).filename == old_filename
        if read_only
        else new_filename
    )

    # Check that modifying other fields always fails
    response = api_client.patch(
        reverse("files:manifest-api-detail", kwargs={"pk": manifest1.id}),
        {"upload_confirmed": "2022-02-02"},
    )
    assert response.status_code == 405
