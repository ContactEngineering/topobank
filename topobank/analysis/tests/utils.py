
import factory
import logging
import pickle
import datetime
from factory.helpers import post_generation

from ..models import Analysis, AnalysisFunction, AnalysisFunctionImplementation
from topobank.manager.tests.utils import TopographyFactory
from topobank.manager.models import Topography

_log = logging.getLogger(__name__)


#
# Define factories for creating test objects
#
class AnalysisFunctionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AnalysisFunction

    name = factory.Sequence(lambda n: "Test Function no. {}".format(n))
    card_view_flavor = 'simple'


class AnalysisFunctionImplementationFactory(factory.django.DjangoModelFactory):

    function = factory.SubFactory(AnalysisFunctionFactory)
    subject_type = AnalysisFunctionImplementation.SUBJECT_TYPE_TOPOGRAPHY
    pyfunc = 'topography_analysis_function_for_tests'

    class Meta:
        model = AnalysisFunctionImplementation


def _analysis_result(analysis):
    func = analysis.function.python_function(type(analysis.topography))
    result = func(analysis.topography, **pickle.loads(analysis.kwargs))
    return pickle.dumps(result)


def _analysis_default_kwargs(analysis):
    return analysis.function.get_default_kwargs(analysis.topography)


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


