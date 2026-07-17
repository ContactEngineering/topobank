"""
Tests for issue #1341: submit must return a viable (successful/running)
analysis, not the latest of *all* existing analyses.

Ordering the full set by ``task_start_time`` sorts never-run rows (NULL
task_start_time) last in PostgreSQL, so ``.last()`` over the unfiltered set
would return a NOTRUN/PENDING row in preference to an available SUCCESS one.
"""

import pytest
from django.utils import timezone

from topobank.analysis.models import WorkflowResult
from topobank.analysis.workflows import SurfaceSet
from topobank.testing.factories import SurfaceFactory, Topography2DFactory


@pytest.mark.django_db
def test_submit_returns_successful_over_notrun(test_workflow, user_alice):
    surface = SurfaceFactory(created_by=user_alice)
    topo = Topography2DFactory(surface=surface)
    kwargs = test_workflow.clean_kwargs(None)

    def _make(state, start):
        wr = WorkflowResult.objects.create(
            workflow_name=test_workflow.name,
            subject_topography=topo,
            kwargs=kwargs,
            created_by=user_alice,
            task_state=state,
            task_start_time=start,
        )
        wr.permissions.grant_for_user(user_alice, "edit")
        return wr

    success = _make(WorkflowResult.SUCCESS, timezone.now())
    notrun = _make(WorkflowResult.NOTRUN, None)  # NULL task_start_time -> sorts last

    result = test_workflow.submit(user_alice, topo, force_submit=False)

    assert result.pk == success.pk
    assert result.pk != notrun.pk


@pytest.mark.django_db
def test_submit_for_surfaces_returns_successful_over_notrun(test_workflow, user_alice):
    s1 = SurfaceFactory(created_by=user_alice)
    surface_set = SurfaceSet(surfaces=[s1.id])
    kwargs = test_workflow.clean_kwargs(None)

    def _make(state, start):
        wr = WorkflowResult.objects.create(
            workflow_name=test_workflow.name,
            subject_hash=surface_set.subject_hash,
            kwargs=kwargs,
            owned_by_id=s1.owned_by_id,
            created_by=user_alice,
            task_state=state,
            task_start_time=start,
        )
        wr.surfaces.set([s1])
        return wr

    success = _make(WorkflowResult.SUCCESS, timezone.now())
    notrun = _make(WorkflowResult.NOTRUN, None)

    result = test_workflow.submit_for_surfaces(user=user_alice, surfaces=[s1])

    assert result.pk == success.pk
    assert result.pk != notrun.pk
