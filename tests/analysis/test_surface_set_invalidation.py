"""
Tests for invalidation and cleanup of surface-set (M2M) analyses (issue #1340).

Surface-set analyses store their subjects via the ``WorkflowResult.surfaces``
M2M and have ``subject_surface`` NULL, so the invalidation signals and the
custodian must match them through the M2M, not only the legacy subject FKs.
"""

import datetime

import pytest
from django.conf import settings
from django.utils import timezone

from topobank.analysis.custodian import periodic_cleanup
from topobank.analysis.models import WorkflowResult
from topobank.analysis.signals import (
    delete_all_related_analyses,
    pre_delete_topography,
    pre_measurement_save,
)
from topobank.manager.models import Topography
from topobank.testing.factories import SurfaceFactory, Topography2DFactory


def _surface_set_analysis(test_workflow, user, surfaces):
    """Create a surface-set WorkflowResult over the given surfaces."""
    return test_workflow.submit_for_surfaces(user=user, surfaces=list(surfaces))


@pytest.mark.django_db
def test_refresh_cache_deprecates_surface_set_analysis(test_workflow, user_alice):
    s1 = SurfaceFactory(created_by=user_alice)
    s2 = SurfaceFactory(created_by=user_alice)
    other = SurfaceFactory(created_by=user_alice)
    topo = Topography2DFactory(surface=s1)

    affected = _surface_set_analysis(test_workflow, user_alice, [s1, s2])
    unrelated = _surface_set_analysis(test_workflow, user_alice, [other])
    assert affected.deprecation_time is None

    delete_all_related_analyses(sender=Topography, instance=topo)

    affected.refresh_from_db()
    unrelated.refresh_from_db()
    assert affected.deprecation_time is not None
    assert unrelated.deprecation_time is None


@pytest.mark.django_db
def test_new_measurement_deletes_surface_set_analysis(test_workflow, user_alice):
    s1 = SurfaceFactory(created_by=user_alice)
    other = SurfaceFactory(created_by=user_alice)

    affected = _surface_set_analysis(test_workflow, user_alice, [s1])
    unrelated = _surface_set_analysis(test_workflow, user_alice, [other])

    # A brand-new (unsaved) measurement added to s1.
    new_topo = Topography(surface=s1)  # pk is None -> "created" branch
    pre_measurement_save(sender=Topography, instance=new_topo)

    assert not WorkflowResult.objects.filter(pk=affected.pk).exists()
    assert WorkflowResult.objects.filter(pk=unrelated.pk).exists()


@pytest.mark.django_db
def test_new_measurement_does_not_touch_unrelated_surface_analyses(
    test_workflow, user_alice
):
    """A new measurement must not delete surface/tag analyses of other surfaces.

    Regression guard for the ``subject_topography=<unsaved>`` -> ``IS NULL``
    trap: an unsaved instance must be scoped by surface only.
    """
    s1 = SurfaceFactory(created_by=user_alice)
    other = SurfaceFactory(created_by=user_alice)
    # A legacy surface analysis on a *different* surface.
    from topobank.testing.factories import SurfaceAnalysisFactory

    unrelated_surface_analysis = SurfaceAnalysisFactory(subject_surface=other)

    new_topo = Topography(surface=s1)
    pre_measurement_save(sender=Topography, instance=new_topo)

    assert WorkflowResult.objects.filter(
        pk=unrelated_surface_analysis.pk
    ).exists()


@pytest.mark.django_db
def test_delete_topography_deletes_surface_set_analysis(test_workflow, user_alice):
    s1 = SurfaceFactory(created_by=user_alice)
    other = SurfaceFactory(created_by=user_alice)
    topo = Topography2DFactory(surface=s1)

    affected = _surface_set_analysis(test_workflow, user_alice, [s1])
    unrelated = _surface_set_analysis(test_workflow, user_alice, [other])

    pre_delete_topography(sender=Topography, instance=topo)

    assert not WorkflowResult.objects.filter(pk=affected.pk).exists()
    assert WorkflowResult.objects.filter(pk=unrelated.pk).exists()


@pytest.mark.django_db
def test_custodian_reaps_deprecated_surface_set_analysis(test_workflow, user_alice):
    s1 = SurfaceFactory(created_by=user_alice)
    analysis = _surface_set_analysis(test_workflow, user_alice, [s1])
    assert analysis.subject_surface is None  # only reachable via the M2M

    WorkflowResult.objects.filter(pk=analysis.pk).update(
        deprecation_time=timezone.now()
        - settings.TOPOBANK_ANALYSIS_DELETE_DELAY
        - datetime.timedelta(days=1)
    )

    periodic_cleanup()

    assert not WorkflowResult.objects.filter(pk=analysis.pk).exists()


@pytest.mark.django_db
def test_custodian_keeps_recently_deprecated_surface_set_analysis(
    test_workflow, user_alice
):
    s1 = SurfaceFactory(created_by=user_alice)
    analysis = _surface_set_analysis(test_workflow, user_alice, [s1])

    WorkflowResult.objects.filter(pk=analysis.pk).update(
        deprecation_time=timezone.now()
    )

    periodic_cleanup()

    assert WorkflowResult.objects.filter(pk=analysis.pk).exists()
