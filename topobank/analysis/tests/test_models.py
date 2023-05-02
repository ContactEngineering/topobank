import operator

import pytest

import datetime
from django.db.models.functions import Lower
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from topobank.manager.models import Topography
from topobank.manager.tests.utils import two_topos, Topography1DFactory  # needed for fixture
from topobank.manager.tests.utils import Topography2DFactory, SurfaceFactory, SurfaceCollectionFactory, UserFactory

from ..models import Analysis, AnalysisFunction
from .utils import TopographyAnalysisFactory, SurfaceAnalysisFactory, SurfaceCollectionAnalysisFactory

from ..registry import ImplementationMissingAnalysisFunctionException, AnalysisFunctionImplementation, \
    register_implementation
from ..functions import topography_analysis_function_for_tests


@pytest.mark.django_db
def test_topography_as_analysis_subject():
    topo = Topography1DFactory()
    func = AnalysisFunction.objects.get(name="test")
    analysis = TopographyAnalysisFactory(subject=topo, function=func)
    assert analysis.subject == topo


@pytest.mark.django_db
def test_surface_as_analysis_subject():
    surf = SurfaceFactory()
    func = AnalysisFunction.objects.get(name="test")
    analysis = SurfaceAnalysisFactory(subject=surf, function=func)
    assert analysis.subject == surf


@pytest.mark.django_db
def test_surfacecollection_as_analysis_subject():
    s1 = SurfaceFactory()
    s2 = SurfaceFactory()
    s3 = SurfaceFactory()
    sc = SurfaceCollectionFactory(surfaces=[s1, s2, s3])
    func = AnalysisFunction.objects.get(name="test")
    analysis = SurfaceCollectionAnalysisFactory(subject=sc, function=func)
    assert analysis.subject == sc


@pytest.mark.django_db
def test_default_users_for_surface_analysis():
    u1 = UserFactory(name='Alice')
    u2 = UserFactory(name='Bob')
    surf = SurfaceFactory(creator=u1)
    surf.share(u2)
    func = AnalysisFunction.objects.get(name="test")
    analysis = SurfaceAnalysisFactory(subject=surf, function=func)
    assert sorted(analysis.get_default_users(), key=operator.attrgetter('name')) == [u1, u2]


@pytest.mark.django_db
def test_default_users_for_surfacecollection_analysis():
    u1 = UserFactory(name='Alice')
    u2 = UserFactory(name='Bob')
    u3 = UserFactory(name='Kim')
    surf1 = SurfaceFactory(creator=u1)
    surf2 = SurfaceFactory(creator=u2)
    surf1.share(u3)
    surf2.share(u3)
    # Only Kim is allowed to see both surfaces
    sc = SurfaceCollectionFactory(surfaces=[surf1, surf2])
    func = AnalysisFunction.objects.get(name="test")
    analysis = SurfaceCollectionAnalysisFactory(subject=sc, function=func)
    assert sorted(analysis.get_default_users(), key=operator.attrgetter('name')) == [u3]


@pytest.mark.django_db
def test_default_users_for_topography_analysis():
    u1 = UserFactory(name='Alice')
    u2 = UserFactory(name='Bob')
    surf = SurfaceFactory(creator=u1)
    surf.share(u2)
    topo = Topography1DFactory(surface=surf)
    func = AnalysisFunction.objects.get(name="test")
    analysis = TopographyAnalysisFactory(subject=topo, function=func)
    assert sorted(analysis.get_default_users(), key=operator.attrgetter('name')) == [u1, u2]


@pytest.mark.django_db
def test_exception_implementation_missing():
    # We create an implementation for surfaces, but not for analyses
    topo = Topography1DFactory()
    surface = topo.surface
    function = AnalysisFunction.objects.get(name="test")
    analysis = TopographyAnalysisFactory(function=function)
    function.eval(surface)  # that's okay, it's implemented
    with pytest.raises(ImplementationMissingAnalysisFunctionException):
        function.eval(analysis)  # that's not implemented


@pytest.mark.django_db
def test_analysis_function(test_analysis_function):
    ct = ContentType.objects.get_for_model(Topography)
    assert test_analysis_function.python_function(ct) == topography_analysis_function_for_tests
    assert test_analysis_function.get_default_kwargs(ct) == dict(a=1, b="foo")

    surface = SurfaceFactory()
    t = Topography1DFactory(surface=surface)
    result = test_analysis_function.eval(t, a=2, b="bar")
    assert result['comment'] == 'Arguments: a is 2 and b is bar'


@pytest.mark.django_db
def test_analysis_times(two_topos, test_analysis_function):
    import pickle

    now = timezone.now()

    analysis = TopographyAnalysisFactory.create(
            subject=Topography.objects.first(),
            function=test_analysis_function,
            task_state=Analysis.SUCCESS,
            kwargs={'a': 2, 'b': 4},
            start_time=datetime.datetime(2018, 1, 1, 12),
            end_time=datetime.datetime(2018, 1,  1, 13),
    )
    analysis.save()

    assert analysis.creation_time - now < datetime.timedelta(seconds=1)
    assert analysis.start_time == datetime.datetime(2018, 1, 1, 12)
    assert analysis.end_time == datetime.datetime(2018, 1, 1, 13)
    assert analysis.duration == datetime.timedelta(0, 3600)

    assert analysis.get_kwargs_display() == str({'a': 2, 'b': 4})


@pytest.mark.django_db
def test_autoload_analysis_functions():
    # TODO this test has a problem: It's not independent from the available functions
    # At least the functions defined in this app should be available

    from django.core.management import call_command

    call_command('register_analysis_functions')

    # remember number of functions
    num_funcs = AnalysisFunction.objects.count()

    # "test" function should be there
    AnalysisFunction.objects.get(name="test")

    #
    # Call should be idempotent
    #
    call_command('register_analysis_functions')
    assert num_funcs == AnalysisFunction.objects.count()


@pytest.mark.django_db
def test_default_function_kwargs():
    from django.core.management import call_command

    call_command('register_analysis_functions')

    func = AnalysisFunction.objects.get(name='test')

    expected_kwargs = dict(a=1, b="foo")
    ct = ContentType.objects.get_for_model(Topography)
    assert func.get_default_kwargs(ct) == expected_kwargs


@pytest.mark.django_db
def test_current_configuration(settings):

    settings.TRACKED_DEPENDENCIES = [
        ('SurfaceTopography', 'SurfaceTopography.__version__'),
        ('ContactMechanics', 'ContactMechanics.__version__'),
        ('NuMPI', 'NuMPI.__version__'),
        ('muFFT', 'muFFT.version.description()'),
        ('topobank', 'topobank.__version__'),
        ('numpy', 'numpy.version.full_version')
    ]

    from topobank.taskapp.tasks import current_configuration

    config = current_configuration()

    versions = config.versions.order_by(Lower('dependency__import_name'))
    # Lower: Just to have a defined order independent of database used

    assert len(versions) == 6

    v0, v1, v2, v3, v4, v5 = versions


    import ContactMechanics
    assert v0.dependency.import_name == 'ContactMechanics'
    assert v0.number_as_string() == ContactMechanics.__version__

    import muFFT
    assert v1.dependency.import_name == 'muFFT'
    assert v1.number_as_string() == muFFT.version.description()

    import NuMPI
    assert v2.dependency.import_name == 'NuMPI'
    assert v2.number_as_string() == NuMPI.__version__

    import numpy
    assert v3.dependency.import_name == 'numpy'
    assert v3.number_as_string() == numpy.version.full_version

    import SurfaceTopography
    assert v4.dependency.import_name == 'SurfaceTopography'
    assert v4.number_as_string() == SurfaceTopography.__version__

    import topobank
    assert v5.dependency.import_name == 'topobank'
    assert v5.number_as_string() == topobank.__version__





