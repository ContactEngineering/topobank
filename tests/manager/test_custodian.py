"""Tests for the periodic cleanup task in topobank.manager.custodian."""

import datetime

import pytest
from django.utils import timezone

from topobank.manager.custodian import periodic_cleanup
from topobank.manager.models import Surface
from topobank.testing.factories import SurfaceFactory


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
