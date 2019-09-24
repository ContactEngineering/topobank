import pytest
import pickle

from topobank.analysis.models import Analysis
from topobank.analysis.models import AnalysisFunction
from topobank.analysis.utils import request_analysis, submit_analysis

from topobank.analysis.tests.utils import AnalysisFactory
from topobank.manager.tests.utils import TopographyFactory, UserFactory

@pytest.mark.django_db
def test_request_analysis(mocker):
    "Make sure analysis objects were created with correct parameters"

    user = UserFactory()

    m = mocker.patch('topobank.analysis.models.AnalysisFunction.python_function', new_callable=mocker.PropertyMock)
    m.return_value = lambda topography, a, b, bins=15, window='hann': None # defining default parameters here

    af = AnalysisFunction(name='somefunc', pyfunc='height_distribution')
    af.save() # needed otherwise analysis cannot be saved later (why?)

    #mocker.patch('topobank.analysis.models.Analysis.objects.create')
    #mocker.patch('django.db.models.QuerySet.delete') # we don't need to test with delete here
    mocker.patch('topobank.taskapp.tasks.perform_analysis.delay') # we don't want to calculate anything

    topo = TopographyFactory()

    # just an abbreviation
    def assert_correct_args(analysis, expected_kwargs):
        kwargs = pickle.loads(analysis.kwargs)
        assert expected_kwargs == kwargs
        assert user in analysis.users.all() # make sure the user has been set


    # mocker.patch('django.db.models.QuerySet.filter')  # we don't need to filter here and analysis has no id
    # test case 1
    analysis = request_analysis(user, af, topo, a=1, b=2)
    assert_correct_args(analysis,
                        dict(a=1,
                             b=2,
                             bins=15,
                             window='hann')) # check default parameters in database


    # test case 2
    analysis = request_analysis(user, af, topo, 1, 2, bins=10)
    assert_correct_args(analysis,
                        dict(a=1,
                             b=2,
                             bins=10,
                             window='hann'))

    # test case 3
    analysis = request_analysis(user, af, topo, 2, 1, window='hamming', bins=5)
    assert_correct_args(analysis,
                        dict(a=2,
                             b=1,
                             bins=5,
                             window='hamming'))


@pytest.mark.django_db
def test_unmark_other_analyses_during_request_analysis(mocker):
    """
    When requesting an analysis with new arguments, the old analyses should still exist
    (at the moment, maybe delete later analyses without user),
    but only the latest one should be marked as "used" by the user
    """
    user = UserFactory()

    m = mocker.patch('topobank.analysis.models.AnalysisFunction.python_function', new_callable=mocker.PropertyMock)
    m.return_value = lambda topography, a, b, bins=15, window='hann': None

    af = AnalysisFunction(name='somefunc', pyfunc='height_distribution')
    af.save()

    topo = TopographyFactory()

    a1 = AnalysisFactory(topography=topo, function=af, kwargs=pickle.dumps(dict(a=9, b=19)), users=[])
    a2 = AnalysisFactory(topography=topo, function=af, kwargs=pickle.dumps(dict(a=29, b=39)), users=[user])

    a3 = request_analysis(user, af, topo, a=1, b=2)

    #
    # Now there are three analyses for af+topo
    #
    assert Analysis.objects.filter(topography=topo, function=af).count() == 3

    #
    # Only one analysis is marked for user 'user'
    #
    analyses = Analysis.objects.filter(topography=topo, function=af, users__in=[user])

    assert len(analyses) == 1

    assert a1 not in analyses
    assert a2 not in analyses
    assert a3 in analyses

    assert pickle.loads(analyses[0].kwargs) == dict(a=1, b=2, bins=15, window='hann')




