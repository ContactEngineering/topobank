"""Tests for the periodic cleanup task in topobank.manager.custodian."""

import datetime

import pytest
from django.utils import timezone

from topobank.manager.custodian import periodic_cleanup
from topobank.manager.models import Surface, Topography
from topobank.testing.factories import SurfaceFactory, Topography2DFactory


@pytest.mark.django_db
def test_periodic_cleanup_no_data():
    # With nothing marked for deletion the task is a no-op and must not fail.
    periodic_cleanup()


@pytest.mark.django_db
def test_periodic_cleanup_deletes_old_marked_surface():
    surface = SurfaceFactory()
    # Mark for deletion further in the past than TOPOBANK_DELETE_DELAY (7 days).
    old = timezone.now() - datetime.timedelta(days=8)
    Surface.all_objects.filter(pk=surface.pk).update(deletion_time=old)
    assert Surface.all_objects.filter(pk=surface.pk).exists()

    periodic_cleanup()

    assert not Surface.all_objects.filter(pk=surface.pk).exists()


@pytest.mark.django_db
def test_periodic_cleanup_keeps_recently_marked_surface():
    surface = SurfaceFactory()
    # Marked for deletion just now -> still within the grace period.
    Surface.all_objects.filter(pk=surface.pk).update(deletion_time=timezone.now())

    periodic_cleanup()

    assert Surface.all_objects.filter(pk=surface.pk).exists()


@pytest.mark.django_db
def test_periodic_cleanup_deletes_orphaned_surface():
    surface = SurfaceFactory()
    # A surface with neither creator nor owner is considered orphaned.
    Surface.all_objects.filter(pk=surface.pk).update(
        created_by=None, owned_by=None
    )

    periodic_cleanup()

    assert not Surface.all_objects.filter(pk=surface.pk).exists()


@pytest.mark.django_db
def test_periodic_cleanup_deletes_old_marked_topography():
    surface = SurfaceFactory()
    topo = Topography2DFactory(surface=surface)
    old = timezone.now() - datetime.timedelta(days=8)
    Topography.all_objects.filter(pk=topo.pk).update(deletion_time=old)

    periodic_cleanup()

    assert not Topography.all_objects.filter(pk=topo.pk).exists()


@pytest.mark.django_db
def test_periodic_cleanup_deletes_old_zip_container():
    from topobank.manager.zip_model import ZipContainer
    from topobank.testing.mock_auth.authorization.models import PermissionSet

    permissions = PermissionSet.objects.create()
    container = ZipContainer.objects.create(permissions=permissions)
    old = timezone.now() - datetime.timedelta(days=8)
    # updated_at is auto_now; bypass it with a queryset update.
    ZipContainer.objects.filter(pk=container.pk).update(updated_at=old)

    periodic_cleanup()

    assert not ZipContainer.objects.filter(pk=container.pk).exists()


@pytest.mark.django_db
def test_periodic_cleanup_deletes_unlinked_manifest():
    from topobank.files.models import Manifest
    from topobank.testing.mock_auth.authorization.models import PermissionSet

    permissions = PermissionSet.objects.create()
    # An unconfirmed manifest with no file that is old enough to be cleaned up.
    manifest = Manifest.objects.create(
        permissions=permissions, filename="orphan.txt", kind="raw"
    )
    old = timezone.now() - datetime.timedelta(days=8)
    # An unset FileField saves as "" rather than NULL; force NULL so the manifest
    # matches the custodian's `file__isnull=True` filter.
    Manifest.objects.filter(pk=manifest.pk).update(created_at=old, file=None)

    periodic_cleanup()

    assert not Manifest.objects.filter(pk=manifest.pk).exists()
