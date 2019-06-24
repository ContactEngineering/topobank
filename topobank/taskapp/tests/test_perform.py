import pytest
import pickle

from ..tasks import perform_analysis

from topobank.analysis.models import Analysis
from topobank.analysis.models import AnalysisFunction
from topobank.manager.models import Topography
from topobank.manager.tests.utils import two_topos

@pytest.mark.django_db
def test_perform_analysis(mocker, two_topos, settings):

    def my_func(topography, a, b, bins=15, window='hann', progress_recorder=None):
        return {
            'topotype': type(topography),
            'x': (a+b)*bins,
            's': window
        }

    m = mocker.patch('topobank.analysis.models.AnalysisFunction.python_function', new_callable=mocker.PropertyMock)
    m.return_value = my_func


    af = AnalysisFunction.objects.first() # doesn't matter
    topo = Topography.objects.first() # doesn't matter

    func_kwargs = dict(a=1,
                       b=2,
                       bins=10,
                       window="hamming")

    analysis = Analysis.objects.create(
                                topography=topo,
                                function=af,
                                kwargs=pickle.dumps(func_kwargs))
    analysis.save()

    settings.CELERY_ALWAYS_EAGER = True # perform tasks locally

    # with mocker.patch('django.conf.settings.CELERY_ALWAYS_EAGER', True, create=True):
    perform_analysis(analysis.id)

    # now check result
    analysis = Analysis.objects.get(id=analysis.id)
    assert pickle.loads(analysis.result) == {
        'topotype': type(topo.topography()),
        'x': 30,
        's': 'hamming'
    }


@pytest.mark.django_db
def test_delete_old_analyses(mocker, two_topos, settings):

    def my_func(topography, a, b, bins=15, window='hann', progress_recorder=None):
        return {
            'topotype': type(topography),
            'x': (a+b)*bins,
            's': window
        }

    m = mocker.patch('topobank.analysis.models.AnalysisFunction.python_function', new_callable=mocker.PropertyMock)
    m.return_value = my_func


    af = AnalysisFunction.objects.first() # doesn't matter
    topo = Topography.objects.first() # doesn't matter

    func_kwargs_seq = [dict(a=1,
                            b=2,
                            bins=10,
                            window="hamming"),
                       dict(a=1,
                            b=2,
                            bins=20,
                            window="hamming"),
                       dict(a=1,
                            b=2,
                            bins=30,
                            window="hamming")]
    states = [Analysis.FAILURE, Analysis.SUCCESS, Analysis.PENDING]

    analysis_ids = []
    for kw, task_state in zip(func_kwargs_seq, states):
        analysis = Analysis.objects.create(
                                    topography=topo,
                                    function=af,
                                    kwargs=pickle.dumps(kw),
                                    task_state=task_state)
        analysis.save()
        analysis_ids.append(analysis.id)

    settings.CELERY_ALWAYS_EAGER = True # perform tasks locally

    # perform only last analysis
    perform_analysis(analysis_ids[-1])

    #
    # Now there should be only one analysis
    #
    assert Analysis.objects.filter(topography=topo, function=af).count() == 1

    # Check result, if it is the right one
    analysis = Analysis.objects.get(id=analysis_ids[-1])
    assert pickle.loads(analysis.result) == {
        'topotype': type(topo.topography()),
        'x': 90,
        's': 'hamming'
    }
    assert pickle.loads(analysis.kwargs)['bins'] == 30
