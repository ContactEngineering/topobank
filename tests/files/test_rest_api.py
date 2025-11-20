from pathlib import Path

import pytest
from django.core.files import File
from rest_framework.reverse import reverse

from topobank.authorization.models import PermissionSet, UserPermission
from topobank.files.models import Folder, Manifest
from topobank.files.utils import file_storage_path
from topobank.testing.data import FIXTURE_DATA_DIR
from topobank.testing.factories import FolderFactory, ManifestFactory
from topobank.testing.utils import assert_dict_equal, upload_file


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
        created_by=user_alice,
        kind="raw",
    )

    # File belongs to alice, log in as bob
    api_client.force_login(user_bob)

    # Bob should not be able to get upload instructions
    response = api_client.get(
        reverse("files:manifest-api-detail", kwargs={"pk": manifest.id})
    )
    # Return 404 when user should not know about the existence of the file
    assert response.status_code == 404, response.content

    # Share with bob editable
    manifest.permissions.grant_for_user(user_bob, "edit")

    # Bob is now able to get upload instructions and upload the file
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
    permissions.grant_for_user(user_alice, "view")
    folder = Folder.objects.create(permissions=permissions, read_only=read_only)
    manifest1 = Manifest.objects.create(
        permissions=permissions,
        folder=folder,
        filename="dektak-1.csv",
        file=File(open(f"{FIXTURE_DATA_DIR}/dektak-1.csv", "rb")),
    )
    Manifest.objects.create(
        permissions=permissions,
        folder=folder,
        filename="dummy.txt",
        file=File(open(f"{FIXTURE_DATA_DIR}/dummy.txt", "rb")),
    )

    # Try deleting file1 - no permission
    response = api_client.delete(
        reverse("files:manifest-api-detail", kwargs={"pk": manifest1.id})
    )
    assert response.status_code == 403

    # Login user
    api_client.force_login(user_alice)

    # Try deleting file - still no permission because alice only has "view" access
    response = api_client.delete(
        reverse("files:manifest-api-detail", kwargs={"pk": manifest1.id})
    )
    assert response.status_code == 403
    assert Manifest.objects.count() == 2

    # Try deleting file - alice needs full access and permission is granted only if
    # folder is not read only
    permissions.grant_for_user(user_alice, "full")
    response = api_client.delete(
        reverse("files:manifest-api-detail", kwargs={"pk": manifest1.id})
    )
    assert response.status_code == (403 if read_only else 204)
    assert Manifest.objects.count() == (2 if read_only else 1)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "read_only,read_only2", [[True, True], [True, False], [False, True], [False, False]]
)
def test_modify_file(
    api_client, user_alice, read_only, read_only2, handle_usage_statistics
):
    permissions = PermissionSet.objects.create()
    permissions.grant_for_user(user_alice, "view")
    folder = Folder.objects.create(permissions=permissions, read_only=read_only)
    manifest1 = Manifest.objects.create(
        permissions=permissions,
        folder=folder,
        filename="dektak-1.csv",
        file=File(open(f"{FIXTURE_DATA_DIR}/dektak-1.csv", "rb")),
    )
    Manifest.objects.create(
        permissions=permissions,
        folder=folder,
        filename="dummy.txt",
        file=File(open(f"{FIXTURE_DATA_DIR}/dummy.txt", "rb")),
    )

    # We should not be able to see the manifest when not logged in
    response = api_client.get(
        reverse("files:manifest-api-detail", kwargs={"pk": manifest1.id})
    )
    # FIXME - This should be 401 - see comment in test_create_file
    assert response.status_code == 404

    old_filename = manifest1.filename
    new_filename = "new_filename.testing"

    # Try patching metadata of file1 - no permission
    response = api_client.patch(
        reverse("files:manifest-api-detail", kwargs={"pk": manifest1.id}),
        {"filename": new_filename},
    )
    # FIXME - This should be 401 - see comment in test_create_file
    assert response.status_code == 403

    # Login user
    api_client.force_login(user_alice)

    # Try patching file - should always fail because alice has view permission
    response = api_client.patch(
        reverse("files:manifest-api-detail", kwargs={"pk": manifest1.id}),
        {"filename": new_filename},
    )
    assert response.status_code == 403

    # If we give alice edit permission, it should only fail if the folder is read-only
    permissions.grant_for_user(user_alice, "edit")
    response = api_client.patch(
        reverse("files:manifest-api-detail", kwargs={"pk": manifest1.id}),
        {"filename": new_filename},
    )
    assert response.status_code == (403 if read_only else 200)
    assert Manifest.objects.get(pk=manifest1.pk).filename == (
        old_filename if read_only else new_filename
    )

    # Check that modifying other fields always fails
    response = api_client.patch(
        reverse("files:manifest-api-detail", kwargs={"pk": manifest1.id}),
        {"confirmed_at": "2022-02-02"},
    )
    assert response.status_code == (403 if read_only else 400)

    # We make a new folder for which alice has "view" access
    permissions = PermissionSet.objects.create()
    permissions.grant_for_user(user_alice, "view")
    folder2 = Folder.objects.create(permissions=permissions, read_only=read_only2)

    # Alice should not be able to move the file to that folder
    response = api_client.patch(
        reverse("files:manifest-api-detail", kwargs={"pk": manifest1.id}),
        {"folder": folder2.get_absolute_url(response.wsgi_request)},
    )
    assert response.status_code == 403

    # Alice should be able to move the file only if she has "edit" access
    permissions.grant_for_user(user_alice, "edit")
    response = api_client.patch(
        reverse("files:manifest-api-detail", kwargs={"pk": manifest1.id}),
        {"folder": folder2.get_absolute_url(response.wsgi_request)},
    )
    assert response.status_code == (403 if read_only or read_only2 else 200)

    # Check that the files appear to have moved
    assert folder.files.count() == (2 if read_only or read_only2 else 1)
    assert folder2.files.count() == (0 if read_only or read_only2 else 1)


@pytest.mark.django_db
@pytest.mark.parametrize("read_only", [True, False])
def test_create_file(api_client, user_alice, read_only, handle_usage_statistics):
    permissions = PermissionSet.objects.create()
    permissions.grant_for_user(user_alice, "view")
    folder = Folder.objects.create(permissions=permissions, read_only=read_only)

    filename = "my_created_file.testing"

    response = api_client.get(
        reverse("files:folder-api-detail", kwargs={"pk": folder.id})  # list_manifests - function-based view
    )
    # User is not logged in, should get 401
    # FIXME - Currently topobank allows anonymous user to call this endpoint if it is a read request so the
    #  authentication is not enforced. This results in 404 because the folder is not visible to anonymous
    #  users. We should enforce authentication and return 401 for unauthenticated users.
    assert response.status_code == 404

    # Try creating a file - no permission
    response = api_client.post(
        reverse("files:manifest-api-list"),  # FileManifestViewSet
        {
            "filename": filename,
            "folder": folder.get_absolute_url(response.wsgi_request),
        },
    )
    # FIXME - User is not logged in, should get 401 - see comment above
    # This one returns 403 because the POST endpoint enforces authentication
    # but because of settings, the authentication layers do not return the 401 status code
    # Instead, the permission check in the view returns 403 because the anonymous user has no access
    assert response.status_code == 403

    # Login user
    api_client.force_login(user_alice)

    # Try creating file without folder - show always fail
    response = api_client.post(
        reverse("files:manifest-api-list"),
        {"filename": filename},
    )
    assert response.status_code == 400, response.status_code

    # Try creating file - permission only if folder is not read only
    response = api_client.post(
        reverse("files:manifest-api-list"),
        {
            "filename": filename,
            "folder": folder.get_absolute_url(response.wsgi_request),
        },
    )
    assert response.status_code == (403 if read_only else 201)
    assert Manifest.objects.count() == (0 if read_only else 1)


def test_list_folder(api_client, user_alice):
    folder = FolderFactory(user=user_alice)
    manifest1 = ManifestFactory(folder=folder)
    manifest2 = ManifestFactory(folder=folder)

    api_client.force_login(user_alice)

    response = api_client.get(
        reverse("files:folder-api-detail", kwargs={"pk": folder.id})
    )

    d = response.data
    del d[manifest1.filename]["file"]
    del d[manifest2.filename]["file"]

    assert_dict_equal(
        d,
        {
            manifest1.filename: {
                "id": manifest1.id,
                "url": f"http://testserver/files/manifest/{manifest1.id}/",
                "filename": manifest1.filename,
                "folder": f"http://testserver/files/folder/{folder.id}/",
                "kind": "N/A",
                "created": manifest1.created_at.astimezone().isoformat(),
                "updated": manifest1.updated_at.astimezone().isoformat(),
                "uploaded_by": None,
                "confirmed_at": manifest1.confirmed_at.astimezone().isoformat(),
                "upload_instructions": None,
            },
            manifest2.filename: {
                "id": manifest2.id,
                "url": f"http://testserver/files/manifest/{manifest2.id}/",
                "filename": manifest2.filename,
                "folder": f"http://testserver/files/folder/{folder.id}/",
                "kind": "N/A",
                "created": manifest2.created_at.astimezone().isoformat(),
                "updated": manifest2.updated_at.astimezone().isoformat(),
                "uploaded_by": None,
                "confirmed_at": manifest2.confirmed_at.astimezone().isoformat(),
                "upload_instructions": None,
            },
        },
    )
