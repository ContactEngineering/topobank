"""
Tests for soft-delete bookkeeping on Surface and Measurement.

`lazy_delete` records the user who performed the deletion in `deleted_by`, on
the object itself and on everything the call cascades to, so a recycle-bin view
can report who deleted what while the object is still recoverable.
"""

import pytest

from topobank.manager.models import Measurement, Surface
from topobank.testing.factories import (
    SurfaceFactory,
    Topography1DFactory,
    UserFactory,
)


@pytest.mark.django_db
def test_surface_lazy_delete_records_deleting_user():
    user = UserFactory()
    surface = SurfaceFactory(created_by=user)

    surface.lazy_delete(deleted_by=user)

    surface.refresh_from_db()
    assert surface.deleted_at is not None
    assert surface.deleted_by == user


@pytest.mark.django_db
def test_surface_lazy_delete_cascades_deleted_by_to_measurements():
    user = UserFactory()
    surface = SurfaceFactory(created_by=user)
    topo = Topography1DFactory(surface=surface)

    surface.lazy_delete(deleted_by=user)

    topo.refresh_from_db()
    assert topo.deleted_at == surface.deleted_at
    assert topo.deleted_by == user


@pytest.mark.django_db
def test_surface_lazy_delete_defaults_to_no_user():
    # System deletions have no actor; the field stays NULL rather than guessing.
    surface = SurfaceFactory(created_by=UserFactory())
    topo = Topography1DFactory(surface=surface)

    surface.lazy_delete()

    surface.refresh_from_db()
    topo.refresh_from_db()
    assert surface.deleted_at is not None
    assert surface.deleted_by is None
    assert topo.deleted_by is None


@pytest.mark.django_db
def test_surface_lazy_delete_leaves_already_deleted_measurements_alone():
    # A measurement deleted earlier keeps its own actor and timestamp; only
    # measurements this call cascades to are stamped.
    first_user = UserFactory()
    second_user = UserFactory()
    surface = SurfaceFactory(created_by=first_user)
    early = Topography1DFactory(surface=surface, name="early")
    late = Topography1DFactory(surface=surface, name="late")

    early.lazy_delete(deleted_by=first_user)
    surface.lazy_delete(deleted_by=second_user)

    early.refresh_from_db()
    late.refresh_from_db()
    assert early.deleted_by == first_user
    assert late.deleted_by == second_user


@pytest.mark.django_db
def test_measurement_lazy_delete_records_deleting_user():
    user = UserFactory()
    surface = SurfaceFactory(created_by=user)
    topo = Topography1DFactory(surface=surface)

    topo.lazy_delete(deleted_by=user)

    topo.refresh_from_db()
    assert topo.deleted_at is not None
    assert topo.deleted_by == user
    # The dataset itself is untouched by a measurement-level delete.
    surface.refresh_from_db()
    assert surface.deleted_at is None
    assert surface.deleted_by is None


@pytest.mark.django_db
def test_deleted_by_is_cleared_when_the_user_is_deleted():
    # SET_NULL: removing a user must not take their deleted datasets with them.
    user = UserFactory()
    surface = SurfaceFactory(created_by=UserFactory())
    surface.lazy_delete(deleted_by=user)

    user.delete()

    surface = Surface.all_objects.get(pk=surface.pk)
    assert surface.deleted_at is not None
    assert surface.deleted_by is None


@pytest.mark.django_db
def test_default_manager_still_hides_soft_deleted_objects():
    user = UserFactory()
    surface = SurfaceFactory(created_by=user)
    topo = Topography1DFactory(surface=surface)

    surface.lazy_delete(deleted_by=user)

    assert not Surface.objects.filter(pk=surface.pk).exists()
    assert Surface.all_objects.filter(pk=surface.pk).exists()
    assert not Measurement.objects.filter(pk=topo.pk).exists()
    assert Measurement.all_objects.filter(pk=topo.pk).exists()
