import datetime

import pytest
from django.contrib.contenttypes.models import ContentType

from topobank.analysis.controller import AnalysisController
from topobank.analysis.models import WorkflowResult
from topobank.analysis.utils import (
    filter_and_order_analyses,
    find_children,
    merge_dicts,
    round_to_significant_digits,
)
from topobank.manager.models import Surface, Topography
from topobank.testing.factories import TopographyAnalysisFactory, UserFactory


@pytest.mark.django_db
def test_request_analysis(two_topos, test_workflow):
    topo1 = Topography.objects.get(name="Example 3 - ZSensor")
    topo2 = Topography.objects.get(name="Example 4 - Default")

    # delete all prior analyses for these two topographies in order to have a clean state
    WorkflowResult.objects.filter(
        subject_topography__in=[topo1, topo2]
    ).delete()

    user = topo1.created_by

    analysis = test_workflow.submit(user=user, subject=topo1)

    assert analysis.subject == topo1
    assert analysis.function == test_workflow
    assert analysis.has_permission(user, "view")


@pytest.mark.django_db
def test_latest_analyses(two_topos, test_workflow):
    topo1 = Topography.objects.get(name="Example 3 - ZSensor")
    topo2 = Topography.objects.get(name="Example 4 - Default")

    user = topo1.created_by

    # delete all prior analyses for these two topographies in order to have a clean state
    WorkflowResult.objects.filter(
        subject_topography__in=[topo1, topo2]
    ).delete()

    #
    # Topography 1
    #
    TopographyAnalysisFactory.create(
        user=user,
        subject_topography=topo1,
        workflow_name=test_workflow.name,
        task_state=WorkflowResult.SUCCESS,
        kwargs=test_workflow.get_default_kwargs(),
        task_start_time=datetime.datetime(2018, 1, 1, 12),
        task_end_time=datetime.datetime(2018, 1, 1, 13, 1, 1),
    )

    # save a second only, which has a later start time
    TopographyAnalysisFactory.create(
        user=user,
        subject_topography=topo1,
        workflow_name=test_workflow.name,
        task_state=WorkflowResult.SUCCESS,
        kwargs=test_workflow.get_default_kwargs(),
        task_start_time=datetime.datetime(2018, 1, 2, 12),
        task_end_time=datetime.datetime(2018, 1, 2, 13, 1, 1),
    )

    #
    # Topography 2
    #
    TopographyAnalysisFactory.create(
        user=user,
        subject_topography=topo2,
        workflow_name=test_workflow.name,
        task_state=WorkflowResult.SUCCESS,
        kwargs=test_workflow.get_default_kwargs(),
        task_start_time=datetime.datetime(2018, 1, 3, 12),
        task_end_time=datetime.datetime(2018, 1, 3, 13, 1, 1),
    )

    # save a second one, which has the latest start time
    TopographyAnalysisFactory.create(
        user=user,
        subject_topography=topo2,
        workflow_name=test_workflow.name,
        task_state=WorkflowResult.SUCCESS,
        kwargs=test_workflow.get_default_kwargs(),
        task_start_time=datetime.datetime(2018, 1, 5, 12),
        task_end_time=datetime.datetime(2018, 1, 5, 13, 1, 1),
    )

    # save a third one, which has a later start time than the first
    TopographyAnalysisFactory.create(
        user=user,
        subject_topography=topo2,
        workflow_name=test_workflow.name,
        task_state=WorkflowResult.SUCCESS,
        kwargs=test_workflow.get_default_kwargs(),
        task_start_time=datetime.datetime(2018, 1, 4, 12),
        task_end_time=datetime.datetime(2018, 1, 4, 13, 1, 1),
    )

    ContentType.objects.get_for_model(Topography)
    analyses = AnalysisController(
        user, subjects=[topo1, topo2], workflow=test_workflow
    )

    assert len(analyses) == 2  # one analysis per function and topography

    # both topographies should be in there

    (at1,) = AnalysisController(
        user, subjects=[topo1], workflow=test_workflow
    ).get()
    (at2,) = AnalysisController(
        user, subjects=[topo2], workflow=test_workflow
    ).get()

    from zoneinfo import ZoneInfo

    from django.conf import settings

    tz = ZoneInfo(settings.TIME_ZONE)

    assert at1.task_start_time == datetime.datetime(2018, 1, 2, 12, tzinfo=tz)
    assert at2.task_start_time == datetime.datetime(2018, 1, 5, 12, tzinfo=tz)


@pytest.mark.django_db
def test_latest_analyses_if_no_analyses(test_workflow):
    user = UserFactory()
    assert (
        WorkflowResult.objects.filter(
            permissions__user_permissions__user=user, workflow_name=test_workflow.name
        ).count()
        == 0
    )


@pytest.mark.django_db
def test_find_children(user_three_topographies_three_surfaces_three_tags):
    topo1, topo2, topo3 = Topography.objects.all()
    surf1, surf2, surf3 = Surface.objects.all()

    assert set(find_children([surf1, surf2, topo3])) == set(
        [surf1, surf2, topo1, topo2, topo3]
    )


def test_merge_dicts():

    # test merging two dictionaries
    dict1 = {"a": 1, "b": 2}
    dict2 = {"b": 3, "c": 4}
    merged = merge_dicts(dict1, [dict2])
    assert merged == {"a": 1, "b": 3, "c": 4}

    # test merging three dictionaries
    dict1 = {"a": 1, "b": 2}
    dict2 = {"b": {"p": 3}, "c": 4}
    dict3 = {"b": {"o": 3}, "c": {"e": 5}}
    merged = merge_dicts(dict1, [dict2, dict3])
    assert merged == {"a": 1, "b": {"o": 3, "p": 3}, "c": {"e": 5}}


def test_find_children_none_returns_none():
    assert find_children(None) is None


def test_round_to_significant_digits():
    import math

    # Rounds to the requested number of significant digits.
    assert round_to_significant_digits(123.456, 2) == 120
    assert round_to_significant_digits(0.00123456, 3) == 0.00123
    assert round_to_significant_digits(-987.0, 1) == -1000

    # NaN is passed through unchanged.
    assert math.isnan(round_to_significant_digits(float("nan"), 3))

    # Zero triggers the math-domain error branch and is returned unchanged.
    assert round_to_significant_digits(0.0, 3) == 0.0


def test_filter_and_order_analyses_empty():
    # No analyses in, no analyses out (exercises the empty-input path).
    assert filter_and_order_analyses([]) == []


@pytest.mark.django_db
def test_filter_and_order_analyses_surface_before_its_topographies(test_workflow):
    import topobank.testing.workflows  # noqa: F401  (registers the workflow)
    from topobank.testing.factories import (
        SurfaceAnalysisFactory,
        SurfaceFactory,
        Topography2DFactory,
    )

    user = UserFactory()
    surface = SurfaceFactory(created_by=user)
    topo1 = Topography2DFactory(surface=surface)
    topo2 = Topography2DFactory(surface=surface)

    ta1 = TopographyAnalysisFactory(
        subject_topography=topo1, workflow_name=test_workflow.name, result=None
    )
    ta2 = TopographyAnalysisFactory(
        subject_topography=topo2, workflow_name=test_workflow.name, result=None
    )
    sa = SurfaceAnalysisFactory(
        subject_surface=surface, workflow_name=test_workflow.name, result=None
    )

    ordered = filter_and_order_analyses([ta2, sa, ta1])

    # The surface has more than one topography, so its (averaged) analysis is
    # kept and placed before the corresponding topography analyses.
    assert set(ordered) == {sa, ta1, ta2}
    assert ordered.index(sa) < ordered.index(ta1)
    assert ordered.index(sa) < ordered.index(ta2)


@pytest.mark.django_db
def test_filter_and_order_analyses_drops_surface_analysis_for_single_topography(
    test_workflow,
):
    import topobank.testing.workflows  # noqa: F401

    from topobank.testing.factories import (
        SurfaceAnalysisFactory,
        SurfaceFactory,
        Topography2DFactory,
    )

    user = UserFactory()
    surface = SurfaceFactory(created_by=user)
    topo = Topography2DFactory(surface=surface)

    ta = TopographyAnalysisFactory(
        subject_topography=topo, workflow_name=test_workflow.name, result=None
    )
    sa = SurfaceAnalysisFactory(
        subject_surface=surface, workflow_name=test_workflow.name, result=None
    )

    ordered = filter_and_order_analyses([ta, sa])

    # With only one topography the surface-level (averaged) analysis is dropped.
    assert ta in ordered
    assert sa not in ordered
