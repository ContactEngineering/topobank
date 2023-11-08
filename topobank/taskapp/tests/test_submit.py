import pytest

from ...manager.tests.utils import Topography1DFactory, UserFactory

from ...analysis.models import Analysis
from ...analysis.controller import request_analysis
from ...analysis.tests.utils import TopographyAnalysisFactory


@pytest.mark.django_db
def test_request_analysis(mocker, test_analysis_function):
    """Make sure analysis objects were created with correct parameters"""

    user = UserFactory()

    af = test_analysis_function

    # m = mocker.patch('topobank.analysis.models.AnalysisFunctionImplementation.python_function',
    #                  new_callable=mocker.PropertyMock)
    # m.return_value = lambda: lambda topography, a, b, bins=15, window='hann': None  # defining default parameters here

    # mocker.patch('topobank.analysis.models.Analysis.objects.create')
    # mocker.patch('django.db.models.QuerySet.delete') # we don't need to test with delete here
    mocker.patch('topobank.taskapp.utils.run_task')  # we don't want to calculate anything

    topo = Topography1DFactory()

    # just an abbreviation
    def assert_correct_args(analysis, expected_kwargs):
        kwargs = analysis.kwargs
        assert kwargs == expected_kwargs
        assert user in analysis.users.all()  # make sure the user has been set

    # test case 1
    analysis = request_analysis(user, af, topo, a=13, b=24)
    assert_correct_args(analysis,
                        dict(a=13,
                             b=24))


    # test case 2
    analysis = request_analysis(user, af, topo, 1, 2)
    assert_correct_args(analysis,
                        dict(a=1,
                             b=2))

    # test case 3
    analysis = request_analysis(user, af, topo, 2, 1)
    assert_correct_args(analysis,
                        dict(a=2,
                             b=1))

    # test case 4
    analysis = request_analysis(user, af, topo, a=1, c=24)  # Parameter c does not exist and will be sanitized
    assert_correct_args(analysis,
                        dict(a=1,
                             b='foo'))  # this is the default parameter


@pytest.mark.django_db
def test_unmark_other_analyses_during_request_analysis(mocker, test_analysis_function):
    """
    When requesting an analysis with new arguments, the old analyses should still exist
    (at the moment, maybe delete later analyses without user),
    but only the latest one should be marked as "used" by the user
    """
    user = UserFactory()

    m = mocker.patch('topobank.analysis.registry.AnalysisFunctionImplementation.python_function',
                     new_callable=mocker.PropertyMock)
    m.return_value = lambda topography, a, b, bins=15, window='hann': None

    af = test_analysis_function

    topo = Topography1DFactory()

    a1 = TopographyAnalysisFactory(subject_topography=topo, function=af, kwargs=dict(a=9, b=19), users=[])
    a2 = TopographyAnalysisFactory(subject_topography=topo, function=af, kwargs=dict(a=29, b=39), users=[user])

    a3 = request_analysis(user, af, topo, a=1, b=2)

    #
    # Now there are three analyses for af+topo
    #
    assert Analysis.objects.filter(subject_dispatch__topography=topo, function=af).count() == 3

    #
    # Only one analysis is marked for user 'user'
    #
    analyses = Analysis.objects.filter(subject_dispatch__topography=topo, function=af, users__in=[user])

    assert len(analyses) == 1

    assert a1 not in analyses
    assert a2 not in analyses
    assert a3 in analyses

    assert analyses[0].kwargs == dict(a=1, b=2)




