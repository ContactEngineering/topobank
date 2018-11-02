import pytest
import pickle

from ..tasks import perform_analysis

from topobank.analysis.models import Analysis
from topobank.analysis.models import AnalysisFunction
from topobank.manager.models import Topography
from topobank.manager.tests.utils import two_topos

@pytest.mark.django_db
def test_perform_analysis(mocker, two_topos, settings):

    # we fake a function in the functions modul which would be built
    # by the eval function
    eval_mock = mocker.patch('builtins.eval')

    def my_func(topography, a, b, bins=15, window='hann'):
        return {
            'topotype': type(topography),
            'x': (a+b)*bins,
            's': window
        }

    eval_mock.return_value = my_func

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


