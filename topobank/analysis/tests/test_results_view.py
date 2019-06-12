"""
Test for results view.
"""

import pytest
import datetime
import pickle
import numpy as np

from django.urls import reverse

from ..models import Analysis, AnalysisFunction
from topobank.manager.tests.utils import two_topos # needed for fixture, see arguments below
from topobank.manager.models import Topography, Surface
from topobank.manager.tests.utils import export_reponse_as_html, \
    SurfaceFactory, UserFactory, TopographyFactory
from .utils import AnalysisFactory, AnalysisFunctionFactory
from topobank.utils import assert_in_content, assert_not_in_content

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
def test_analysis_times(client, two_topos):

    username = 'testuser'
    password = 'abcd$1234'

    assert client.login(username=username, password=password)

    topo = Topography.objects.first()
    af = AnalysisFunction.objects.first()

    pickled_result = pickle.dumps({'name': 'test function',
                                   'xlabel': 'x',
                                   'ylabel': 'y',
                                   'xunit': '1',
                                   'yunit': '1',
                                   'series': [],
                                   })

    analysis = Analysis.objects.create(
        topography=topo,
        function=af,
        task_state=Analysis.SUCCESS,
        kwargs=pickle.dumps({}),
        start_time=datetime.datetime(2018, 1, 1, 12),
        end_time=datetime.datetime(2018, 1, 1, 13, 1, 1), # duration: 1 hour, 1 minute, 1 sec
        result=pickled_result,
    )
    analysis.save()

    response = client.get(reverse("analysis:card"),
                           data={
                               'topography_ids[]': [topo.id],
                               'function_id': af.id,
                               'card_id': "card-1",
                               'template_flavor': 'list',
                           },
                           HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                           follow=True)

    assert response.status_code == 200

    # export_reponse_as_html(response, fname='/tmp/response-analysis-times.html')

    assert b"2018-01-01 12:00:00" in response.content # start
    # assert b"2018-01-01 13:01:01" in response.content # end, lef out for now
    assert b"1:01:01" in response.content # duration

@pytest.mark.django_db
def test_show_only_last_analysis(client, two_topos):
    # TODO use mocks for topographies if possible

    username = 'testuser'
    password = 'abcd$1234'

    assert client.login(username=username, password=password)

    topo1 = Topography.objects.first()
    topo2 = Topography.objects.last()
    af = AnalysisFunction.objects.first()

    pickled_result = pickle.dumps({'name': 'test function',
                                   'xlabel': 'x',
                                   'ylabel': 'y',
                                   'xunit': '1',
                                   'yunit': '1',
                                   'series': [],
                                   })

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
        result=pickled_result,
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
        result=pickled_result,
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
        result=pickled_result,
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
        result=pickled_result,
    )
    analysis.save()

    #
    # Check response, for both topographies only the
    # latest results should be shown
    #
    response = client.get(reverse("analysis:card"),
                           data={
                               'topography_ids[]': [topo1.id, topo2.id],
                               'function_id': af.id,
                               'card_idx': 1,
                               'template_flavor': 'list'
                           },
                          HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                          follow=True)

    assert response.status_code == 200

    # export_reponse_as_html(response)

    assert b"2018-01-02 12:00:00" in response.content
    assert b"2018-01-04 12:00:00" in response.content

    assert b"2018-01-01 12:00:00" not in response.content
    assert b"2018-01-03 12:00:00" not in response.content

@pytest.mark.django_db
def test_show_analyses_with_different_arguments(client, two_topos):
    # TODO use mocks for topographies if possible or factories

    username = 'testuser'
    password = 'abcd$1234'

    assert client.login(username=username, password=password)

    topo1 = Topography.objects.first()
    af = AnalysisFunction.objects.first()

    pickled_result = pickle.dumps({'name': 'test function',
                                   'xlabel': 'x',
                                   'ylabel': 'y',
                                   'xunit': '1',
                                   'yunit': '1',
                                   'series': [],
                                   })

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
        result=pickled_result,
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
        result=pickled_result,
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
        result=pickled_result,
    )
    analysis.save()

    #
    # Check response, all three analyses should be shown
    #
    response = client.get(reverse("analysis:card"),
                           data={
                               'topography_ids[]': [topo1.id],
                               'function_id': af.id,
                               'card_id': "card-1",
                               'template_flavor': 'list'
                           },
                           HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                           follow=True)

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

@pytest.fixture
def ids_downloadable_analyses():
    #
    # create two analyses with resuls
    #
    topos = [Topography.objects.get(name="Example 3 - ZSensor"), Topography.objects.get(name="Example 4 - Default")]
    function = AnalysisFunction.objects.create(name="Test Function", pyfunc='dummy', automatic=False)

    v = np.arange(5)
    ids = []

    for k in range(2):
        result = dict(
            name=f'Test Results {k}',
            scalars=dict(
                nice_value=13,
                bad_value=-99,
            ),
            xlabel='time',
            ylabel='distance',
            xunit='s',
            yunit='m',
            series=[
                dict(name='First Series',
                     x=v + k,
                     y=2 * v + k,
                     ),
                dict(name='Second Series',
                     x=v + 1 + k,
                     y=3 * (v + 1) + k,
                     )
            ])

        analysis = Analysis.objects.create(topography=topos[k],
                                           function=function,
                                           result=pickle.dumps(result),
                                           kwargs=pickle.dumps({}))
        ids.append(analysis.id)

    return ids

@pytest.mark.django_db
def test_analyis_download_as_txt(client, two_topos, ids_downloadable_analyses):

    username = 'testuser'
    password = 'abcd$1234'

    assert client.login(username=username, password=password)

    ids_str = ",".join(str(i) for i in ids_downloadable_analyses)
    download_url = reverse('analysis:download-txt', kwargs=dict(ids=ids_str))

    response = client.get(download_url)


    from io import StringIO

    txt = response.content.decode()

    assert "Test Function" in txt # function name should be in there

    # remove comments and empty lines
    filtered_lines = []
    for line in txt.splitlines():
        line = line.strip()
        if not line.startswith('#') and len(line)>0:
            filtered_lines.append(line)
    filtered_txt = "\n".join(filtered_lines)

    arr = np.loadtxt(StringIO(filtered_txt))

    expected_arr = np.array([
        (0, 0),
        (1, 2),
        (2, 4),
        (3, 6),
        (4, 8),
        (1, 3),
        (2, 6),
        (3, 9),
        (4, 12),
        (5, 15),
        (1, 1),
        (2, 3),
        (3, 5),
        (4, 7),
        (5, 9),
        (2, 4),
        (3, 7),
        (4, 10),
        (5, 13),
        (6, 16),
    ])

    assert arr == pytest.approx(expected_arr)

@pytest.mark.django_db
def test_analyis_download_as_xlsx(client, two_topos, ids_downloadable_analyses):

    username = 'testuser'
    password = 'abcd$1234'

    assert client.login(username=username, password=password)

    ids_str = ",".join(str(i) for i in ids_downloadable_analyses)
    download_url = reverse('analysis:download-xlsx', kwargs=dict(ids=ids_str))

    response = client.get(download_url)

    import tempfile, openpyxl

    tmp = tempfile.NamedTemporaryFile(suffix='.xlsx') # will be deleted automatically
    tmp.write(response.content)
    tmp.seek(0)

    xlsx = openpyxl.load_workbook(tmp.name)

    assert len(xlsx.worksheets) == 2*2 + 1 # TODO this would currently fail if the topographies had the same name

    ws = xlsx.get_sheet_by_name("Example 3 - ZSensor - First Series")

    assert list(ws.values) == [
        (None, 'time (s)', 'distance (m)'),
        (0, 0, 0),
        (1, 1, 2),
        (2, 2, 4),
        (3, 3, 6),
        (4, 4, 8),
    ]

    ws = xlsx.get_sheet_by_name("Example 3 - ZSensor - Second Series")

    assert list(ws.values) == [
        (None, 'time (s)', 'distance (m)'),
        (0, 1, 3),
        (1, 2, 6),
        (2, 3, 9),
        (3, 4, 12),
        (4, 5, 15),
    ]

    ws = xlsx.get_sheet_by_name("Example 4 - Default - First Series")

    assert list(ws.values) == [
        (None, 'time (s)', 'distance (m)'),
        (0, 1, 1),
        (1, 2, 3),
        (2, 3, 5),
        (3, 4, 7),
        (4, 5, 9),
    ]

    ws = xlsx.get_sheet_by_name("Example 4 - Default - Second Series")

    assert list(ws.values) == [
        (None, 'time (s)', 'distance (m)'),
        (0, 2, 4),
        (1, 3, 7),
        (2, 4, 10),
        (3, 5, 13),
        (4, 6, 16),
    ]


@pytest.mark.django_db
def test_view_shared_analysis_results(client):

    password = 'abcd$1234'

    #
    # create database objects
    #
    user1 = UserFactory(password=password)
    user2 = UserFactory(password=password)

    surface1 = SurfaceFactory(creator=user1)
    surface2 = SurfaceFactory(creator=user2)

    # user2 shares surfaces, so user 1 should see surface1+surface2
    surface2.share(user1)

    # create topographies + functions + analyses
    func1 = AnalysisFunctionFactory()
    #func2 = AnalysisFunctionFactory()

    # Two topographies for surface1
    topo1a = TopographyFactory(surface=surface1, name='topo1a')
    topo1b = TopographyFactory(surface=surface1, name='topo1b')

    # One topography for surface2
    topo2a = TopographyFactory(surface=surface2, name='topo2a')

    # analyses, differentiate by start time
    analysis1a_1 = AnalysisFactory(topography=topo1a, function=func1,
                                   start_time=datetime.datetime(2019, 1, 1, 12))
    analysis1b_1 = AnalysisFactory(topography=topo1b, function=func1,
                                   start_time=datetime.datetime(2019, 1, 1, 13))
    analysis2a_1 = AnalysisFactory(topography=topo2a, function=func1,
                                   start_time=datetime.datetime(2019, 1, 1, 14))

    # analysis1a_2 = AnalysisFactory(topography=topo1a, function=func2,
    #                                start_time=datetime.datetime(2019, 1, 1, 15))
    # analysis1b_2 = AnalysisFactory(topography=topo1b, function=func2,
    #                                start_time=datetime.datetime(2019, 1, 1, 16))
    # analysis2a_2 = AnalysisFactory(topography=topo2a, function=func2,
    #                                start_time=datetime.datetime(2019, 1, 1, 17))

    #
    # Now we change to the analysis card view and look what we get
    #
    assert client.login(username=user1.username, password=password)

    response = client.get(reverse("analysis:card"),
                          data={
                              'topography_ids[]': [topo1a.id, topo1b.id, topo2a.id],
                              'function_id': func1.id,
                              'card_idx': 1,
                              'template_flavor': 'list'
                          },
                          HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                          follow=True)

    assert response.status_code == 200

    # We should see start times of all three topographies
    assert_in_content(response, '2019-01-01 12:00:00')  # topo1a
    assert_in_content(response, '2019-01-01 13:00:00')  # topo1b
    assert_in_content(response, '2019-01-01 14:00:00')  # topo2a

    client.logout()

    #
    # user 2 cannot access results from topo1, it is not shared
    #
    assert client.login(username=user2.username, password=password)

    response = client.get(reverse("analysis:card"),
                          data={
                              'topography_ids[]': [topo1a.id, topo1b.id, topo2a.id],
                              'function_id': func1.id,
                              'card_idx': 1,
                              'template_flavor': 'list'
                          },
                          HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                          follow=True)

    assert response.status_code == 200

    assert_not_in_content(response, '2019-01-01 12:00:00')  # topo1a
    assert_not_in_content(response, '2019-01-01 13:00:00')  # topo1b
    assert_in_content(response, '2019-01-01 14:00:00')  # topo2a

    client.logout()
