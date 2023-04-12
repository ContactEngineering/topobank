from dataclasses import dataclass
import logging
import pickle
import datetime
import numpy as np


from django.contrib.contenttypes.models import ContentType
import factory
import pytest

from ..models import Analysis, AnalysisFunction
from topobank.manager.tests.utils import Topography2DFactory, SurfaceFactory, SurfaceCollectionFactory
from SurfaceTopography import Topography as STTopography, NonuniformLineScan as STNonuniformLineScan

_log = logging.getLogger(__name__)


#
# Define factories for creating test objects
#
class AnalysisFunctionFactory(factory.django.DjangoModelFactory):
    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = AnalysisFunction

    name = factory.Sequence(lambda n: "Test Function no. {}".format(n))

#
# class AnalysisFunctionImplementationFactory(factory.django.DjangoModelFactory):
#
#     function = factory.SubFactory(AnalysisFunctionFactory)
#     subject_type = factory.LazyAttribute(lambda x: ContentType.objects.get_for_model(Topography))
#     code_ref = 'topography_analysis_function_for_tests'
#
#     # noinspection PyMissingOrEmptyDocstring
#     class Meta:
#         model = AnalysisFunctionImplementation


def _analysis_result(analysis):
    func = analysis.function.python_function(ContentType.objects.get_for_model(analysis.subject))
    result = func(analysis.subject, **analysis.kwargs)
    return result


def _analysis_pickled_default_kwargs(analysis):
    subject_type = ContentType.objects.get_for_model(analysis.subject)
    return analysis.function.get_default_kwargs(subject_type)


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

    function = factory.SubFactory(AnalysisFunctionFactory)
    subject = factory.SubFactory(Topography2DFactory)  # Does this work with a generic subject?

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
            users = set(s.creator for s in self.related_surfaces())
            self.users.set(users)

        if extracted:
            # a list of users was passed in, add those users
            for user in extracted:
                self.users.add(user)


class TopographyAnalysisFactory(AnalysisFactory):
    """Create an analysis for a topography."""
    subject = factory.SubFactory(Topography2DFactory)

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = Analysis


class SurfaceAnalysisFactory(AnalysisFactory):
    """Create an analysis for a surface."""
    subject = factory.SubFactory(SurfaceFactory)

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = Analysis


class SurfaceCollectionAnalysisFactory(AnalysisFactory):
    """Create an analysis for a surface collection."""
    subject = factory.SubFactory(SurfaceCollectionFactory)

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = Analysis


@dataclass(frozen=True)
class FakeTopographyModel:
    """This model is used to create a Topography for being passed to analysis functions.
    """
    t: STTopography
    name: str = "mytopo"
    is_periodic: bool = False

    def topography(self):
        """Return low level topography.
        """
        return self.t

    def get_absolute_url(self):
        return "some/url/"


class DummyProgressRecorder:
    def set_progress(self, a, nsteps):
        """Do nothing."""
        pass  # dummy



@pytest.fixture
def simple_linear_2d_topography():
    """Simple 2D topography, which is linear in y"""
    unit = 'nm'
    y = np.arange(10).reshape((1, -1))
    x = np.arange(5).reshape((-1, 1))
    arr = -2 * y + 0 * x  # only slope in y direction
    t = STTopography(arr, (5, 10), unit=unit).detrend('center')
    return t



@pytest.fixture
def simple_surface():
    class WrapTopography:
        def __init__(self, t):
            self._t = t
        def topography(self):
            return self._t

    class WrapRequest:
        def __init__(self, c):
            self._c = c
        def all(self):
            return self._c

    class WrapSurface:
        def __init__(self, c):
            self._c = c
        @property
        def topography_set(self):
            return WrapRequest(self._c)

    nx, ny = 113, 123
    sx, sy = 1, 1
    lx = 0.3
    topographies = [
        STTopography(np.resize(np.sin(np.arange(nx) * sx * 2 * np.pi / (nx * lx)), (nx, ny)), (sx, sy), periodic=False,
                     unit='um')
    ]

    nx = 278
    sx = 100
    lx = 2
    x = np.arange(nx) * sx / nx
    topographies += [
        STNonuniformLineScan(x, np.cos(x * np.pi / lx), unit='nm')
    ]

    return WrapSurface([WrapTopography(t) for t in topographies])


