import pytest
import pickle

from ..tasks import submit_analysis

from topobank.analysis.models import Analysis
from topobank.analysis.models import AnalysisFunction

from topobank.analysis.tests.utils import AnalysisFactory
from topobank.manager.tests.utils import TopographyFactory

@pytest.mark.django_db
def test_submit(mocker):

    m = mocker.patch('topobank.analysis.models.AnalysisFunction.python_function', new_callable=mocker.PropertyMock)
    m.return_value = lambda topography, a, b, bins=15, window='hann': None

    af = AnalysisFunction(name='somefunc', pyfunc='height_distribution')

    mocker.patch('topobank.analysis.models.Analysis.objects.create')
    mocker.patch('django.db.models.QuerySet.delete') # we don't need to test with delete here

    topo = TopographyFactory()

    # just an abbreviation
    def assert_correct_args(expected_kwargs):
        Analysis.objects.create.assert_called_with(function=af,
                                                   topography=topo,
                                                   task_state=Analysis.PENDING,
                                                   kwargs=pickle.dumps(expected_kwargs))

    mocker.patch('django.db.models.QuerySet.filter')  # we don't need to filter here and analysis has no id
    # test case 1
    submit_analysis(af, topo, a=1, b=2)
    assert_correct_args(dict(a=1,
                             b=2,
                             bins=15,
                             window='hann'))


    # test case 2
    submit_analysis(af, topo, 1, 2, bins=10)
    assert_correct_args(dict(a=1,
                             b=2,
                             bins=10,
                             window='hann'))

    # test case 3
    submit_analysis(af, topo, 2, 1, window='hamming', bins=5)
    assert_correct_args(dict(a=2,
                             b=1,
                             bins=5,
                             window='hamming'))


@pytest.mark.django_db
def test_delete_old_analyses_during_submit(mocker):


    m = mocker.patch('topobank.analysis.models.AnalysisFunction.python_function', new_callable=mocker.PropertyMock)
    m.return_value = lambda topography, a, b, bins=15, window='hann': None

    af = AnalysisFunction(name='somefunc', pyfunc='height_distribution')
    af.save()

    topo = TopographyFactory()

    a1 = AnalysisFactory(topography=topo, function=af, kwargs=pickle.dumps(dict(a=9, b=19)))
    a2 = AnalysisFactory(topography=topo, function=af, kwargs=pickle.dumps(dict(a=29, b=39)))

    submit_analysis(af, topo, a=1, b=2)

    #
    # Only one analysis should be left
    #
    analyses = Analysis.objects.filter(topography=topo, function=af)

    assert len(analyses) == 1

    assert a1 not in analyses
    assert a2 not in analyses

    assert pickle.loads(analyses[0].kwargs) == dict(a=1, b=2, bins=15, window='hann')




