
import factory
import logging
import pickle
import datetime

from ..models import Analysis, AnalysisFunction
from topobank.manager.tests.utils import TopographyFactory

_log = logging.getLogger(__name__)

#
# Define factories for creating test objects
#
class AnalysisFunctionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AnalysisFunction

    name = factory.Sequence(lambda n: "heights-after-scale-by-{}".format(n))
    automatic = True
    pyfunc = "test_function" # this function exists in topobank.analysis.functions


def _analysis_result(analysis):
    result = analysis.function.python_function(analysis.topography, **pickle.loads(analysis.kwargs))
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

    @factory.post_generation
    def users(self, create, extracted, **kwargs):
        if create:
            self.users.set([self.topography.surface.creator])

        if extracted:
            # a list of users was passed in, add those users
            for user in extracted:
                self.users.add(user)

