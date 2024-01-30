import datetime
import logging
from dataclasses import dataclass

import factory
import numpy as np
import pytest
from django.contrib.contenttypes.models import ContentType
from SurfaceTopography import NonuniformLineScan as STNonuniformLineScan
from SurfaceTopography import Topography as STTopography

from ...manager.tests.utils import SurfaceCollectionFactory, SurfaceFactory, Topography2DFactory
from ..models import Analysis, AnalysisFunction, AnalysisSubject

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
    func = analysis.function.get_python_function(ContentType.objects.get_for_model(analysis.subject_dispatch.get()))
    result = func(analysis.subject_dispatch.get(), **analysis.kwargs)
    return result


def _failed_analysis_result(analysis):
    return {'message': 'This analysis has failed.'}


def _analysis_default_kwargs(analysis):
    subject_type = ContentType.objects.get_for_model(analysis.subject_dispatch.get())
    return analysis.function.get_default_kwargs(subject_type)


class AnalysisSubjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AnalysisSubject


class AnalysisFactory(factory.django.DjangoModelFactory):
    """Abstract factory class for generating Analysis.

    For real analyses for Topographies or Surfaces use the
    child classes.
    """

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        # model = Analysis
        abstract = True
        exclude = ['subject_topography', 'subject_surface', 'subject_collection']

    subject_topography = None  # factory.SubFactory(Topography2DFactory)
    subject_surface = None
    subject_collection = None

    function = factory.SubFactory(AnalysisFunctionFactory)
    subject_dispatch = factory.SubFactory(AnalysisSubjectFactory,
                                          topography=factory.SelfAttribute('..subject_topography'),
                                          surface=factory.SelfAttribute('..subject_surface'),
                                          collection=factory.SelfAttribute('..subject_collection'))

    kwargs = factory.LazyAttribute(_analysis_default_kwargs)
    result = factory.LazyAttribute(_analysis_result)

    task_state = Analysis.SUCCESS

    start_time = factory.LazyFunction(lambda: datetime.datetime.now() - datetime.timedelta(0, 1))
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

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = Analysis

    subject_topography = factory.SubFactory(Topography2DFactory)


class FailedTopographyAnalysisFactory(AnalysisFactory):
    """Create an analysis for a topography."""

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = Analysis

    subject_topography = factory.SubFactory(Topography2DFactory)
    result = factory.LazyAttribute(_failed_analysis_result)


class SurfaceAnalysisFactory(AnalysisFactory):
    """Create an analysis for a surface."""

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = Analysis

    subject_surface = factory.SubFactory(SurfaceFactory)


class SurfaceCollectionAnalysisFactory(AnalysisFactory):
    """Create an analysis for a surface collection."""

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = Analysis

    subject_collection = factory.SubFactory(SurfaceCollectionFactory)


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
