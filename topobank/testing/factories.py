import datetime
import logging
from dataclasses import dataclass

import factory
import numpy as np
import pytest
from django.contrib.contenttypes.models import ContentType
from SurfaceTopography import NonuniformLineScan as STNonuniformLineScan
from SurfaceTopography import Topography as STTopography

from .data import FIXTURE_DATA_DIR

from ..analysis.models import Analysis, AnalysisFunction, AnalysisSubject
from ..manager.models import Surface, Topography, Tag, Property
from ..organizations.models import Organization

_log = logging.getLogger(__name__)


class OrcidSocialAccountFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = "socialaccount.SocialAccount"

    user_id = 0  # overwrite on construction
    provider = "orcid"
    uid = factory.Sequence(lambda n: "{:04d}-{:04d}-{:04d}-{:04d}".format(n, n, n, n))
    extra_data = {}

    @factory.post_generation
    def set_extra_data(self, create, value, **kwargs):
        self.extra_data = {
            "orcid-identifier": {
                "uri": "https://orcid.org/{}".format(self.uid),
                "path": self.uid,
                "host": "orcid.org",
            }
        }
        self.save()


class UserFactory(factory.django.DjangoModelFactory):
    username = factory.Sequence(lambda n: f"user-{n}")
    email = factory.Sequence(lambda n: f"user-{n}@example.com")
    password = factory.PostGenerationMethodCall("set_password", "password")
    name = factory.Sequence(lambda n: f"name-{n}")

    class Meta:
        model = "users.User"
        django_get_or_create = ("username",)

    @factory.post_generation
    def create_orcid_account(self, create, value, **kwargs):
        OrcidSocialAccountFactory(user_id=self.id)


#
# Define factories for creating test objects
#
class SurfaceFactory(factory.django.DjangoModelFactory):
    """Generates a Surface."""

    class Meta:
        model = Surface

    name = factory.Sequence(
        lambda n: "surface-{:05d}".format(n)
    )  # format because of defined order by name
    creator = factory.SubFactory(UserFactory)


class TagFactory(factory.django.DjangoModelFactory):
    """Generates a Tag."""

    class Meta:
        model = Tag

    name = factory.Sequence(lambda n: "tag-{:05d}".format(n))

    @factory.post_generation
    def surfaces(self, create, extracted, **kwargs):
        if not create:
            # Simple build, do nothing
            return
        if extracted:
            # A list of surfaces were passed in, use them for the manytomany field
            for surface in extracted:
                self.surface_set.add(surface)


class PropertyFactory(factory.django.DjangoModelFactory):
    """Generates a Property."""

    class Meta:
        model = Property

    @factory.post_generation
    def surfaces(self, create, extracted, **kwargs):
        if not create:
            # Simple build, do nothing
            return
        if extracted:
            # A list of surfaces were passed in, use them for the manytomany field
            for surface in extracted:
                self.properties.add(surface)


class Topography1DFactory(factory.django.DjangoModelFactory):
    """
    Generates a 1D Topography.
    """

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = Topography

    surface = factory.SubFactory(SurfaceFactory)
    # creator is set automatically to surface's creator if not set, see signals
    name = factory.Sequence(lambda n: "topography-{:05d}".format(n))
    datafile = factory.django.FileField(from_path=FIXTURE_DATA_DIR + "/line_scan_1.asc")
    data_source = 0
    measurement_date = factory.Sequence(
        lambda n: datetime.date(2019, 1, 1) + datetime.timedelta(days=n)
    )
    size_x = 512
    # if you need size_y, use Topography2DFactory below
    size_editable = False
    unit_editable = False
    height_scale_editable = True
    unit = "nm"
    instrument_name = ""
    instrument_type = Topography.INSTRUMENT_TYPE_UNDEFINED
    instrument_parameters = {}


class Topography2DFactory(Topography1DFactory):
    """
    Generates a 2D Topography.
    """

    size_y = 512
    datafile = factory.django.FileField(from_path=FIXTURE_DATA_DIR + "/10x10.txt")

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = Topography


#
# Define factories for creating test objects
#
class AnalysisFunctionFactory(factory.django.DjangoModelFactory):
    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = AnalysisFunction

    name = factory.Sequence(lambda n: "Test Function no. {}".format(n))


def _analysis_result(analysis):
    func = analysis.function.get_python_function(
        ContentType.objects.get_for_model(analysis.subject_dispatch.get())
    )
    result = func(analysis.subject_dispatch.get(), **analysis.kwargs)
    return result


def _failed_analysis_result(analysis):
    return {"message": "This analysis has failed."}


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
        exclude = ["subject_topography", "subject_surface", "subject_tag"]

    subject_topography = None  # factory.SubFactory(Topography2DFactory)
    subject_surface = None
    subject_tag = None

    function = factory.SubFactory(AnalysisFunctionFactory)
    subject_dispatch = factory.SubFactory(
        AnalysisSubjectFactory,
        topography=factory.SelfAttribute("..subject_topography"),
        surface=factory.SelfAttribute("..subject_surface"),
        tag=factory.SelfAttribute("..subject_tag"),
    )
    user = factory.LazyAttribute(
        lambda obj: (
            obj.subject_surface.creator
            if obj.subject_surface
            else (
                obj.subject_topography.creator
                if obj.subject_topography
                else obj.subject_tag.get_related_surfaces().first().creator
            )
        )
    )

    kwargs = factory.LazyAttribute(_analysis_default_kwargs)
    result = factory.LazyAttribute(_analysis_result)

    task_state = Analysis.SUCCESS

    start_time = factory.LazyFunction(
        lambda: datetime.datetime.now() - datetime.timedelta(0, 1)
    )
    end_time = factory.LazyFunction(datetime.datetime.now)


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


class TagAnalysisFactory(AnalysisFactory):
    """Create an analysis for a surface collection."""

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = Analysis

    subject_tag = factory.SubFactory(TagFactory)


@dataclass(frozen=True)
class FakeTopographyModel:
    """This model is used to create a Topography for being passed to analysis functions."""

    t: STTopography
    name: str = "mytopo"
    is_periodic: bool = False

    def topography(self):
        """Return low level topography."""
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
    unit = "nm"
    y = np.arange(10).reshape((1, -1))
    x = np.arange(5).reshape((-1, 1))
    arr = -2 * y + 0 * x  # only slope in y direction
    t = STTopography(arr, (5, 10), unit=unit).detrend("center")
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
        STTopography(
            np.resize(np.sin(np.arange(nx) * sx * 2 * np.pi / (nx * lx)), (nx, ny)),
            (sx, sy),
            periodic=False,
            unit="um",
        )
    ]

    nx = 278
    sx = 100
    lx = 2
    x = np.arange(nx) * sx / nx
    topographies += [STNonuniformLineScan(x, np.cos(x * np.pi / lx), unit="nm")]

    return WrapSurface([WrapTopography(t) for t in topographies])


class OrganizationFactory(factory.django.DjangoModelFactory):
    """Creating Organization instance for supplib."""

    class Meta:
        model = Organization

    name = factory.Sequence(lambda n: "Organization No. {:d}".format(n))