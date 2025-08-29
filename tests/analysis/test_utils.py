import datetime

import pytest
from django.contrib.contenttypes.models import ContentType

from topobank.analysis.models import WorkflowResult
from topobank.analysis.utils import find_children, merge_dicts
from topobank.analysis.v1.controller import AnalysisController
from topobank.manager.models import Surface, Topography
from topobank.testing.factories import TopographyAnalysisFactory, UserFactory


@pytest.mark.django_db
def test_request_analysis(two_topos, test_analysis_function):
    topo1 = Topography.objects.get(name="Example 3 - ZSensor")
    topo2 = Topography.objects.get(name="Example 4 - Default")

    # delete all prior analyses for these two topographies in order to have a clean state
    WorkflowResult.objects.filter(
        subject_dispatch__topography__in=[topo1, topo2]
    ).delete()

    user = topo1.creator

    analysis = test_analysis_function.submit(user=user, subject=topo1)

    assert analysis.subject == topo1
    assert analysis.function == test_analysis_function
    assert analysis.has_permission(user, "view")


@pytest.mark.django_db
def test_latest_analyses(two_topos, test_analysis_function):
    topo1 = Topography.objects.get(name="Example 3 - ZSensor")
    topo2 = Topography.objects.get(name="Example 4 - Default")

    user = topo1.creator

    # delete all prior analyses for these two topographies in order to have a clean state
    WorkflowResult.objects.filter(
        subject_dispatch__topography__in=[topo1, topo2]
    ).delete()

    #
    # Topography 1
    #
    TopographyAnalysisFactory.create(
        user=user,
        subject_topography=topo1,
        function=test_analysis_function,
        task_state=WorkflowResult.SUCCESS,
        kwargs=test_analysis_function.get_default_kwargs(),
        task_start_time=datetime.datetime(2018, 1, 1, 12),
        task_end_time=datetime.datetime(2018, 1, 1, 13, 1, 1),
    )

    # save a second only, which has a later start time
    TopographyAnalysisFactory.create(
        user=user,
        subject_topography=topo1,
        function=test_analysis_function,
        task_state=WorkflowResult.SUCCESS,
        kwargs=test_analysis_function.get_default_kwargs(),
        task_start_time=datetime.datetime(2018, 1, 2, 12),
        task_end_time=datetime.datetime(2018, 1, 2, 13, 1, 1),
    )

    #
    # Topography 2
    #
    TopographyAnalysisFactory.create(
        user=user,
        subject_topography=topo2,
        function=test_analysis_function,
        task_state=WorkflowResult.SUCCESS,
        kwargs=test_analysis_function.get_default_kwargs(),
        task_start_time=datetime.datetime(2018, 1, 3, 12),
        task_end_time=datetime.datetime(2018, 1, 3, 13, 1, 1),
    )

    # save a second one, which has the latest start time
    TopographyAnalysisFactory.create(
        user=user,
        subject_topography=topo2,
        function=test_analysis_function,
        task_state=WorkflowResult.SUCCESS,
        kwargs=test_analysis_function.get_default_kwargs(),
        task_start_time=datetime.datetime(2018, 1, 5, 12),
        task_end_time=datetime.datetime(2018, 1, 5, 13, 1, 1),
    )

    # save a third one, which has a later start time than the first
    TopographyAnalysisFactory.create(
        user=user,
        subject_topography=topo2,
        function=test_analysis_function,
        task_state=WorkflowResult.SUCCESS,
        kwargs=test_analysis_function.get_default_kwargs(),
        task_start_time=datetime.datetime(2018, 1, 4, 12),
        task_end_time=datetime.datetime(2018, 1, 4, 13, 1, 1),
    )

    ContentType.objects.get_for_model(Topography)
    analyses = AnalysisController(
        user, subjects=[topo1, topo2], workflow=test_analysis_function
    )

    assert len(analyses) == 2  # one analysis per function and topography

    # both topographies should be in there

    (at1,) = AnalysisController(
        user, subjects=[topo1], workflow=test_analysis_function
    ).get()
    (at2,) = AnalysisController(
        user, subjects=[topo2], workflow=test_analysis_function
    ).get()

    import pytz
    from django.conf import settings

    tz = pytz.timezone(settings.TIME_ZONE)

    assert at1.task_start_time == tz.localize(datetime.datetime(2018, 1, 2, 12))
    assert at2.task_start_time == tz.localize(datetime.datetime(2018, 1, 5, 12))


@pytest.mark.django_db
def test_latest_analyses_if_no_analyses(test_analysis_function):
    user = UserFactory()
    assert (
        WorkflowResult.objects.filter(
            permissions__user_permissions__user=user, function=test_analysis_function
        ).count()
        == 0
    )


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
