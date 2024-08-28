from pathlib import Path

import pytest
from rest_framework.reverse import reverse

from topobank.authorization.models import PermissionSet, UserPermission
from topobank.files.models import Folder, Manifest
from topobank.files.utils import generate_storage_path
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
    response = api_client.post(
        reverse("files:upload-finished", kwargs={"manifest_id": manifest.id})
    )
    assert response.status_code == 204, response.content

    manifest = Manifest.objects.get(id=manifest.id)
    assert manifest.file
    assert manifest.filename == name
    assert manifest.file.name == generate_storage_path(manifest, name)
