"""
Regression tests for management commands in topobank.manager.

These exercise the command entry points on a (mostly) empty database. They are
deliberately light-weight: the commands iterate over real objects and do heavy
file I/O in production, so here we only ensure the commands are wired up and run
end-to-end without crashing.
"""

import pytest
from django.core.management import call_command

from topobank.testing.factories import SurfaceFactory


@pytest.mark.django_db
def test_fix_permissions_empty():
    call_command("fix_permissions")


@pytest.mark.django_db
def test_fix_permissions_dry_run():
    call_command("fix_permissions", "--dry-run")


@pytest.mark.django_db
def test_fix_permissions_with_surface():
    # A surface whose creator already has full permission exercises the
    # unpublished branch without changing anything.
    SurfaceFactory()
    call_command("fix_permissions")


@pytest.mark.django_db
def test_refresh_cache_empty():
    call_command("refresh_cache")


@pytest.mark.django_db
def test_set_datafile_format_empty():
    call_command("set_datafile_format")


@pytest.mark.django_db
def test_set_datafile_format_all_dry_run():
    call_command("set_datafile_format", "--all", "--dry-run")
