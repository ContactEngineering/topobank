from django.contrib.contenttypes.models import ContentType
import factory
import logging
import pickle
import datetime
import json

from ..models import Analysis, AnalysisFunction, AnalysisFunctionImplementation
from topobank.manager.tests.utils import TopographyFactory, SurfaceFactory
from topobank.manager.models import Topography, Surface

_log = logging.getLogger(__name__)


#
# Define factories for creating test objects
#
class AnalysisFunctionFactory(factory.django.DjangoModelFactory):
    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = AnalysisFunction

    name = factory.Sequence(lambda n: "Test Function no. {}".format(n))
    card_view_flavor = 'simple'


class AnalysisFunctionImplementationFactory(factory.django.DjangoModelFactory):

    function = factory.SubFactory(AnalysisFunctionFactory)
    subject_type = factory.LazyAttribute(lambda x: ContentType.objects.get_for_model(Topography))
    code_ref = 'topography_analysis_function_for_tests'

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = AnalysisFunctionImplementation


def _analysis_result(analysis):
    func = analysis.function.python_function(ContentType.objects.get_for_model(analysis.subject))
    result = func(analysis.subject, **pickle.loads(analysis.kwargs))
    return pickle.dumps(result)


def _analysis_pickled_default_kwargs(analysis):
    subject_type = ContentType.objects.get_for_model(analysis.subject)
    return pickle.dumps(analysis.function.get_default_kwargs(subject_type))


class AnalysisFactory(factory.django.DjangoModelFactory):
    """Abstract factory class for generating Analysis.

    For real analyses for Topographies or Surfaces use the
    child classes.
    """

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        # model = Analysis
        abstract = True
        exclude = ['subject']
        # See https://factoryboy.readthedocs.io/en/stable/recipes.html#django-models-with-genericforeignkeys

    id = factory.Sequence(lambda n: n)
    function = factory.SubFactory(AnalysisFunctionFactory)
    subject = factory.SubFactory(TopographyFactory)  # Does this work with a generic subject?

    subject_id = factory.SelfAttribute('subject.id')
    subject_type = factory.LazyAttribute(
            lambda o: ContentType.objects.get_for_model(o.subject))

    kwargs = factory.LazyAttribute(_analysis_pickled_default_kwargs)
    result = factory.LazyAttribute(_analysis_result)

    task_state = Analysis.SUCCESS

    start_time = factory.LazyFunction(lambda: datetime.datetime.now()-datetime.timedelta(0, 1))
    end_time = factory.LazyFunction(datetime.datetime.now)

    @factory.post_generation
    def users(self, create, extracted, **kwargs):
        if create:
            surface = self.related_surface
            self.users.set([surface.creator])

        if extracted:
            # a list of users was passed in, add those users
            for user in extracted:
                self.users.add(user)


class TopographyAnalysisFactory(AnalysisFactory):
    """Create an analysis for a topography."""
    subject = factory.SubFactory(TopographyFactory)

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = Analysis


class SurfaceAnalysisFactory(AnalysisFactory):
    """Create an analysis for a surface."""
    subject = factory.SubFactory(SurfaceFactory)

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = Surface


