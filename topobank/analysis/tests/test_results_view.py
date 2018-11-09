"""
Test for results view.
"""

import pytest
import datetime
import pickle

from django.urls import reverse

from ..models import Analysis, AnalysisFunction
from topobank.manager.tests.utils import two_topos
from topobank.manager.models import Topography, Surface
# from topobank.manager.tests.utils import export_reponse_as_html

def selection_from_instances(instances):
    """A little helper for constructing a selection."""
    x = []
    for i in instances:
        prefix = i.__class__.__name__.lower()
        x.append("{}-{}".format(prefix, i.id))

    return x

def test_selection_from_instances(mocker):
    mocker.patch('topobank.manager.models.Topography')
    mocker.patch('topobank.manager.models.Surface')

    instances = [Surface(id=1, name="S1"),
                 Surface(id=2, name="S2"),
                 Topography(id=1, name="T1"),
                 Topography(id=2, name="T2"),
                 Topography(id=3, name="T3"),
                 ]

    expected = [ 'surface-1', 'surface-2', 'topography-1', 'topography-2', 'topography-3']

    assert expected == selection_from_instances(instances)


@pytest.mark.django_db
def test_analysis_times(client, two_topos): # TODO use mocks here if possible

    username = 'testuser'
    password = 'abcd$1234'

    assert client.login(username=username, password=password)

    topo = Topography.objects.first()
    af = AnalysisFunction.objects.first()

    analysis = Analysis.objects.create(
        topography=topo,
        function=af,
        task_state=Analysis.SUCCESS,
        kwargs=pickle.dumps({}),
        start_time=datetime.datetime(2018, 1, 1, 12),
        end_time=datetime.datetime(2018, 1, 1, 13, 1, 1), # duration: 1 hour, 1 minute, 1 sec
    )
    analysis.save()

    response = client.post(reverse("analysis:list"),
                           data={
                               'selection': selection_from_instances([topo]),
                               'functions': [af.id],
                           }, follow=True)

    assert response.status_code == 200

    assert b"2018-01-01 12:00:00" in response.content # start
    # assert b"2018-01-01 13:01:01" in response.content # end, lef out for now
    assert b"1:01:01" in response.content # duration

@pytest.mark.django_db
def test_show_only_last_analysis(client, two_topos):# TODO use mocks here if possible

    username = 'testuser'
    password = 'abcd$1234'

    assert client.login(username=username, password=password)

    topo1 = Topography.objects.first()
    topo2 = Topography.objects.last()
    af = AnalysisFunction.objects.first()

    #
    # Topography 1
    #
    analysis = Analysis.objects.create(
        topography=topo1,
        function=af,
        task_state=Analysis.SUCCESS,
        kwargs=pickle.dumps({}),
        start_time=datetime.datetime(2018, 1, 1, 12),
        end_time=datetime.datetime(2018, 1, 1, 13, 1, 1),
    )
    analysis.save()

    # save a second only, which has a later start time
    analysis = Analysis.objects.create(
        topography=topo1,
        function=af,
        task_state=Analysis.SUCCESS,
        kwargs=pickle.dumps({}),
        start_time=datetime.datetime(2018, 1, 2, 12),
        end_time=datetime.datetime(2018, 1, 2, 13, 1, 1),
    )
    analysis.save()

    #
    # Topography 2
    #
    analysis = Analysis.objects.create(
        topography=topo2,
        function=af,
        task_state=Analysis.SUCCESS,
        kwargs=pickle.dumps({}),
        start_time=datetime.datetime(2018, 1, 3, 12),
        end_time=datetime.datetime(2018, 1, 3, 13, 1, 1),
    )
    analysis.save()

    # save a second only, which has a later start time
    analysis = Analysis.objects.create(
        topography=topo2,
        function=af,
        task_state=Analysis.SUCCESS,
        kwargs=pickle.dumps({}),
        start_time=datetime.datetime(2018, 1, 4, 12),
        end_time=datetime.datetime(2018, 1, 4, 13, 1, 1),
    )
    analysis.save()

    #
    # Check response, for both topographies only the
    # latest results should be shown
    #
    response = client.post(reverse("analysis:list"),
                           data={
                               'selection': selection_from_instances([topo1, topo2]),
                               'functions': [af.id],
                           }, follow=True)

    assert response.status_code == 200

    assert b"2018-01-02 12:00:00" in response.content
    assert b"2018-01-04 12:00:00" in response.content

    assert b"2018-01-01 12:00:00" not in response.content
    assert b"2018-01-03 12:00:00" not in response.content

@pytest.mark.django_db
def test_show_analyses_with_different_arguments(client, two_topos):

    username = 'testuser'
    password = 'abcd$1234'

    assert client.login(username=username, password=password)

    topo1 = Topography.objects.first()
    af = AnalysisFunction.objects.first()

    #
    # Create analyses for same function and topography but with different arguments
    #
    analysis = Analysis.objects.create(
        topography=topo1,
        function=af,
        task_state=Analysis.SUCCESS,
        kwargs=pickle.dumps({'bins':10}),
        start_time=datetime.datetime(2018, 1, 1, 12),
        end_time=datetime.datetime(2018, 1, 1, 13, 1, 1),
    )
    analysis.save()

    # save a second only, which has a later start time
    analysis = Analysis.objects.create(
        topography=topo1,
        function=af,
        task_state=Analysis.SUCCESS,
        kwargs=pickle.dumps({'bins':20}),
        start_time=datetime.datetime(2018, 1, 2, 12),
        end_time=datetime.datetime(2018, 1, 2, 13, 1, 1),
    )
    analysis.save()

    # save a second only, which has a later start time
    analysis = Analysis.objects.create(
        topography=topo1,
        function=af,
        task_state=Analysis.SUCCESS,
        kwargs=pickle.dumps({'bins': 30}),
        start_time=datetime.datetime(2018, 1, 3, 12),
        end_time=datetime.datetime(2018, 1, 3, 13, 1, 1),
    )
    analysis.save()

    #
    # Check response, all three analyses should be shown
    #
    response = client.post(reverse("analysis:list"),
                           data={
                               'selection': selection_from_instances([topo1, ]),
                               'functions': [af.id],
                           }, follow=True)

    assert response.status_code == 200

    assert b"2018-01-01 12:00:00" in response.content
    assert b"2018-01-02 12:00:00" in response.content
    assert b"2018-01-03 12:00:00" in response.content

    # arguments should be visible in output

    import html.parser
    html_parser = html.parser.HTMLParser()
    unescaped = html_parser.unescape(response.content.decode())

    assert str(dict(bins=10)) in unescaped
    assert str(dict(bins=20)) in unescaped

@pytest.mark.django_db
def test_show_multiple_analyses_for_two_functions(client, two_topos):

    username = 'testuser'
    password = 'abcd$1234'

    assert client.login(username=username, password=password)

    topo1 = Topography.objects.first()
    topo2 = Topography.objects.last()
    af1 = AnalysisFunction.objects.first()
    af2 = AnalysisFunction.objects.last()

    assert topo1 != topo2
    assert af1 != af2

    #
    # Create analyses for two functions and two different topographies
    #
    counter = 0
    for af in [af1, af2]:
        for topo in [topo1, topo2]:
            counter += 1
            analysis = Analysis.objects.create(
                topography=topo,
                function=af,
                task_state=Analysis.SUCCESS,
                kwargs=pickle.dumps({'bins':10}),
                start_time=datetime.datetime(2018, 1, 1, counter),
                end_time=datetime.datetime(2018, 1, 1, counter+1),
            )
            analysis.save()

    #
    # Check response when selecting only first function, both analyses should be shown
    #
    response = client.post(reverse("analysis:list"),
                           data={
                               'selection': selection_from_instances([topo1, topo2]),
                               'functions': [af1.id],
                           }, follow=True)

    assert response.status_code == 200

    assert b"Example 3 - ZSensor" in response.content
    assert b"Example 4 - Default" in response.content

    #
    # Check response when selecting only both functions, both analyses should be shown
    #
    response = client.post(reverse("analysis:list"),
                           data={
                               'selection': selection_from_instances([topo1, topo2]),
                               'functions': [af1.id, af2.id],
                           }, follow=True)

    assert response.status_code == 200

    assert b"Example 3 - ZSensor" in response.content
    assert b"Example 4 - Default" in response.content

