"""Tests for topobank.manager.zip_model.ZipContainer."""

import pytest
from django.core.exceptions import PermissionDenied

from topobank.manager.zip_model import ZipContainer
from topobank.testing.factories import UserFactory
from topobank.testing.mock_auth.authorization.models import PermissionSet


def _single_user_permissions(allow="full"):
    user = UserFactory()
    permissions = PermissionSet.objects.create()
    permissions.grant(user, allow)
    return user, permissions


@pytest.mark.django_db
def test_create_empty_manifest():
    _, permissions = _single_user_permissions()
    container = ZipContainer.objects.create(permissions=permissions)
    assert container.manifest is None

    container.create_empty_manifest()

    assert container.manifest is not None
    assert container.manifest.filename == "container.zip"


@pytest.mark.django_db
def test_create_empty_manifest_twice_raises():
    _, permissions = _single_user_permissions()
    container = ZipContainer.objects.create(permissions=permissions)
    container.create_empty_manifest()

    with pytest.raises(RuntimeError):
        container.create_empty_manifest()


@pytest.mark.django_db
def test_task_worker_nothing_to_do():
    # No manifest and no tag / surface ids -> nothing to do, must not raise.
    _, permissions = _single_user_permissions()
    container = ZipContainer.objects.create(permissions=permissions)
    container.task_worker()


@pytest.mark.django_db
def test_task_worker_requires_single_user():
    user_a, permissions = _single_user_permissions()
    permissions.grant(UserFactory(), "view")  # now two users

    container = ZipContainer.objects.create(permissions=permissions)
    with pytest.raises(PermissionDenied):
        container.task_worker()


@pytest.mark.django_db
def test_export_zip_without_target_raises():
    _, permissions = _single_user_permissions()
    container = ZipContainer.objects.create(permissions=permissions)
    with pytest.raises(RuntimeError):
        container.export_zip()
