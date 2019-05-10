
import factory
import logging
import pickle
import datetime
import numpy as np

from ..models import Analysis, AnalysisFunction
from topobank.manager.tests.utils import TopographyFactory
from topobank.taskapp.tasks import _analysis_pyfunc_by_name

_log = logging.getLogger(__name__)

#
# Define factories for creating test objects
#
class AnalysisFunctionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AnalysisFunction

    name = factory.Sequence(lambda n: "heights-after-scale-by-{}".format(n))
    automatic = True

    @factory.sequence
    def pyfunc(n):
        def scale(topography):
            K = 10

            heights = np.arange(K)

            return {
                'name': 'Heights after scale',
                'xlabel': 'index',
                'ylabel': 'height',
                'xunit': 1,
                'yunit': topography.unit,
                'series': [
                    dict(name='Heights by  index',
                         x=range(K),
                         y=heights),
                ]
            }
        return scale

def _analysis_result(analysis):
    result = analysis.function.pyfunc(analysis.topography)
    return pickle.dumps(result)

class AnalysisFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = Analysis

    id = factory.Sequence(lambda n: n)
    function = factory.SubFactory(AnalysisFunctionFactory)
    topography = factory.SubFactory(TopographyFactory)

    kwargs = pickle.dumps({})
    result = factory.LazyAttribute(_analysis_result)

    task_state = Analysis.SUCCESS

    start_time = factory.LazyFunction(lambda: datetime.datetime.now()-datetime.timedelta(0,1))
    end_time = factory.LazyFunction(datetime.datetime.now)

