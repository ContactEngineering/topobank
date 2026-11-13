"""
Tests for issue #1265: results computed before a measurement changed must not
be reused.

Changing e.g. the instrument parameters of a measurement refreshes its cache,
which marks every related WorkflowResult as deprecated (instead of deleting it,
so the custodian can remove it after a delay). Submitting the workflow again
and looking up the latest results must then skip the deprecated rows;
otherwise users who had computed a result before the change keep seeing it,
while users who had not get a fresh one.
"""

import pytest
from django.utils import timezone

from topobank.analysis.controller import AnalysisController
from topobank.analysis.models import WorkflowResult
from topobank.analysis.workflows import SurfaceSet
from topobank.manager.models import Topography, post_refresh_cache
from topobank.testing.factories import SurfaceFactory, Topography2DFactory


def _measurement_changed(topography):
    """What Topography.refresh_cache announces once the cache is renewed."""
    post_refresh_cache.send(sender=Topography, instance=topography)


@pytest.fixture
def topography(user_alice):
    return Topography2DFactory(surface=SurfaceFactory(created_by=user_alice))


@pytest.fixture
def successful_result(test_workflow, user_alice, topography):
    wr = WorkflowResult.objects.create(
        workflow_name=test_workflow.name,
        subject_topography=topography,
        kwargs=test_workflow.clean_kwargs(None),
        created_by=user_alice,
        task_state=WorkflowResult.SUCCESS,
        task_start_time=timezone.now(),
    )
    wr.permissions.grant_for_user(user_alice, "edit")
    return wr


@pytest.mark.django_db
def test_submit_reuses_current_result(
    test_workflow, user_alice, topography, successful_result
):
    # Sanity check for the tests below: without a change, the result is reused
    result = test_workflow.submit(user_alice, topography)
    assert result.pk == successful_result.pk


@pytest.mark.django_db
def test_submit_recomputes_after_measurement_changed(
    test_workflow, user_alice, topography, successful_result
):
    _measurement_changed(topography)
    successful_result.refresh_from_db()
    assert successful_result.deprecation_time is not None

    result = test_workflow.submit(user_alice, topography)

    assert result.pk != successful_result.pk
    assert result.deprecation_time is None
    # The deprecated result is left for the custodian to delete later
    assert WorkflowResult.objects.filter(pk=successful_result.pk).exists()

    # ...and the new result is the one reused from now on
    assert test_workflow.submit(user_alice, topography).pk == result.pk


@pytest.mark.django_db
def test_controller_treats_deprecated_result_as_missing(
    test_workflow, user_alice, topography, successful_result
):
    controller = AnalysisController(
        user_alice, subjects=[topography], workflow=test_workflow
    )
    assert [a.pk for a in controller.get()] == [successful_result.pk]
    assert controller.subjects_without_analysis_results == []

    _measurement_changed(topography)

    controller = AnalysisController(
        user_alice, subjects=[topography], workflow=test_workflow
    )
    assert list(controller.get()) == []
    assert controller.subjects_without_analysis_results == [topography]


@pytest.mark.django_db
def test_submit_for_surfaces_recomputes_after_measurement_changed(
    test_workflow, user_alice, topography
):
    surface = topography.surface
    surface_set = SurfaceSet(surfaces=[surface.id])
    wr = WorkflowResult.objects.create(
        workflow_name=test_workflow.name,
        subject_hash=surface_set.subject_hash,
        kwargs=test_workflow.clean_kwargs(None),
        owned_by_id=surface.owned_by_id,
        created_by=user_alice,
        task_state=WorkflowResult.SUCCESS,
        task_start_time=timezone.now(),
    )
    wr.surfaces.set([surface])
    assert test_workflow.submit_for_surfaces(user_alice, [surface]).pk == wr.pk

    _measurement_changed(topography)

    result = test_workflow.submit_for_surfaces(user_alice, [surface])
    assert result.pk != wr.pk
    assert WorkflowResult.objects.filter(pk=wr.pk).exists()
