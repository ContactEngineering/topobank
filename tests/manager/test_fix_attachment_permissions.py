"""
Tests for the fix_attachment_permissions command (topobank#1414).

The broken states are built the way the old deepcopy code left them: a
published (copied) dataset whose attachment folder still carries the private
original's permission set, either as a copy of the folder (Surface) or as the
very same folder (Topography).
"""

import pytest
from django.core.files.base import ContentFile
from django.core.management import call_command

from topobank.files.models import ManifestSet
from topobank.manager.models import Surface, Topography
from topobank.testing.factories import SurfaceFactory, Topography2DFactory


def _attach(obj, filename="notes.txt", content=b"Some notes"):
    obj.attachments.save_file(filename, "att", ContentFile(content))


def _visible_folder_ids(user):
    return set(ManifestSet.objects.for_user(user, "view").values_list("id", flat=True))


def _run(*args):
    call_command("fix_attachment_permissions", *args)


@pytest.fixture
def original(user_alice):
    """Alice's private surface with an attachment."""
    surface = SurfaceFactory(created_by=user_alice)
    _attach(surface)
    return surface


@pytest.fixture
def published(user_bob):
    """Stands in for the published copy; bob may see it, as may the public."""
    return SurfaceFactory(created_by=user_bob)


@pytest.fixture
def surface_with_foreign_permissions(original, published):
    # What Surface.deepcopy did before 9b7acdd9: copy the folder, keeping the
    # original's permission set
    folder = original.attachments.deepcopy()
    Surface.all_objects.filter(pk=published.pk).update(attachments=folder)
    published.refresh_from_db()
    assert published.attachments.permissions_id == original.permissions_id
    return published


@pytest.mark.django_db
def test_switches_unshared_folder_to_its_surface(
    user_alice, user_bob, original, surface_with_foreign_permissions
):
    published = surface_with_foreign_permissions
    folder_id = published.attachments_id
    assert folder_id not in _visible_folder_ids(user_bob)  # the reported 404

    _run()

    published.refresh_from_db()
    assert published.attachments_id == folder_id  # fixed in place, not copied
    assert published.attachments.permissions_id == published.permissions_id
    assert set(published.attachments.files.values_list("permissions_id", flat=True)) == {
        published.permissions_id
    }
    assert folder_id in _visible_folder_ids(user_bob)
    # Alice keeps her own attachments
    assert original.attachments_id in _visible_folder_ids(user_alice)


@pytest.mark.django_db
def test_copies_folder_shared_with_original_topography(
    user_alice, user_bob, original, published
):
    original_topography = Topography2DFactory(surface=original)
    _attach(original_topography, "private.txt", b"Alice only")
    copied_topography = Topography2DFactory(surface=published)
    # What Topography.deepcopy did before 9b7acdd9: keep the original's folder
    Topography.all_objects.filter(pk=copied_topography.pk).update(
        attachments=original_topography.attachments
    )
    shared_folder_id = original_topography.attachments_id

    _run()

    copied_topography.refresh_from_db()
    original_topography.refresh_from_db()
    # The copy has a folder of its own, with its permissions and the same files
    copied_folder = copied_topography.attachments
    assert copied_folder.id != shared_folder_id
    assert copied_folder.permissions_id == copied_topography.permissions_id
    (copied_file,) = copied_folder.files.all()
    assert copied_file.filename == "private.txt"
    assert copied_file.permissions_id == copied_topography.permissions_id
    with copied_file.file.open("rb") as f:
        assert f.read() == b"Alice only"
    assert copied_folder.id in _visible_folder_ids(user_bob)
    # The original folder is unchanged, so it does not become visible to bob
    assert original_topography.attachments_id == shared_folder_id
    assert original_topography.attachments.permissions_id == original.permissions_id
    assert shared_folder_id not in _visible_folder_ids(user_bob)
    assert shared_folder_id in _visible_folder_ids(user_alice)


@pytest.mark.django_db
def test_dry_run_changes_nothing(surface_with_foreign_permissions):
    published = surface_with_foreign_permissions
    folder_permissions = published.attachments.permissions_id

    _run("--dry-run")

    published.refresh_from_db()
    assert published.attachments.permissions_id == folder_permissions


@pytest.mark.django_db
def test_is_idempotent_and_leaves_correct_folders_alone(
    capsys, original, surface_with_foreign_permissions
):
    folder_before = (original.attachments_id, original.attachments.permissions_id)
    _run()
    capsys.readouterr()

    _run()

    out = capsys.readouterr().out
    assert "Folders switched to their object's permissions: 0" in out
    assert "Shared folders copied for an object: 0" in out
    original.refresh_from_db()
    assert (original.attachments_id, original.attachments.permissions_id) == folder_before
