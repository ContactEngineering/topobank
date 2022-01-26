import pytest
from operator import itemgetter
import datetime
from django.db.models.functions import Lower
from django.contrib.contenttypes.models import ContentType

from ..models import Analysis, AnalysisFunction
from topobank.manager.models import Topography
from topobank.manager.tests.utils import two_topos, Topography1DFactory  # needed for fixture
from .utils import AnalysisFunctionFactory, AnalysisFunctionImplementationFactory, \
    TopographyAnalysisFactory, SurfaceAnalysisFactory, SurfaceFactory
from ..registry import ImplementationMissingException


@pytest.mark.django_db
def test_topography_as_analysis_subject():
    topo = Topography1DFactory()
    # we must have an implementation before creating the analysis
    impl = AnalysisFunctionImplementationFactory(code_ref='topography_analysis_function_for_tests',
                                                 subject_type=ContentType.objects.get_for_model(topo))
    analysis = TopographyAnalysisFactory(subject=topo, function=impl.function)
    assert analysis.subject == topo


@pytest.mark.django_db
def test_surface_as_analysis_subject():
    surf = SurfaceFactory()
    # we must have an implementation before creating the analysis
    impl = AnalysisFunctionImplementationFactory(code_ref='surface_analysis_function_for_tests',
                                                 subject_type=ContentType.objects.get_for_model(surf))
    analysis = SurfaceAnalysisFactory(subject=surf, function=impl.function)
    assert analysis.subject == surf


@pytest.mark.django_db
def test_exception_implementation_missing():
    # We create an implementation for surfaces, but not for topographies
    topo = Topography1DFactory()
    surface = topo.surface

    impl = AnalysisFunctionImplementationFactory(code_ref='surface_analysis_function_for_tests',
                                                 subject_type=ContentType.objects.get_for_model(surface))
    function = impl.function

    function.eval(surface)  # that's okay, it's implemented
    with pytest.raises(ImplementationMissingException):
        function.eval(topo)  # that's not implemented


@pytest.mark.django_db
def test_analysis_function_implementation():
    impl = AnalysisFunctionImplementationFactory()
    from ..functions import topography_analysis_function_for_tests

    assert impl.python_function() == topography_analysis_function_for_tests
    assert impl.get_default_kwargs() == dict(a=1, b="foo")

    t = Topography1DFactory()
    result = impl.eval(t, a=2, b="bar")
    assert result['comment'] == f"a is 2 and b is bar"


@pytest.mark.django_db
def test_analysis_function():
    func = AnalysisFunctionFactory()
    impl = AnalysisFunctionImplementationFactory(function=func)
    from ..functions import topography_analysis_function_for_tests

    ct = ContentType.objects.get_for_model(Topography)
    assert func.python_function(ct) == topography_analysis_function_for_tests
    assert func.get_default_kwargs(ct) == dict(a=1, b="foo")

    t = Topography1DFactory()
    result = func.eval(t, a=2, b="bar")
    assert result['comment'] == f"a is 2 and b is bar"


@pytest.mark.django_db
def test_analysis_times(two_topos):

    import pickle

    analysis = TopographyAnalysisFactory.create(
            subject=Topography.objects.first(),
            function=AnalysisFunction.objects.first(),
            task_state=Analysis.SUCCESS,
            kwargs=pickle.dumps({'bins': 2, 'wfac': 4}),
            start_time=datetime.datetime(2018, 1, 1, 12),
            end_time=datetime.datetime(2018, 1,  1, 13),
    )
    analysis.save()

    assert analysis.start_time == datetime.datetime(2018, 1, 1, 12)
    assert analysis.end_time == datetime.datetime(2018, 1, 1, 13)
    assert analysis.duration() == datetime.timedelta(0, 3600)

    assert analysis.get_kwargs_display() == str({'bins': 2, 'wfac': 4})


# @pytest.mark.skip("Cannot run startup code which modifies the database so far.")
@pytest.mark.django_db
def test_autoload_analysis_functions():
    # TODO this test has a problem: It's not independent from the available functions

    from django.core.management import call_command

    call_command('register_analysis_functions')

    funcs = AnalysisFunction.objects.all().order_by('name')

    expected_funcs = sorted([
        dict(name='Height distribution',),
        dict(name='Slope distribution'),
        dict(name='Curvature distribution'),
        dict(name='Power spectrum'),
        dict(name='Autocorrelation'),
        dict(name='Variable bandwidth'),
        dict(name='Contact mechanics'),
        dict(name='Roughness parameters'),
        dict(name='Scale-dependent slope'),
        dict(name='Scale-dependent curvature'),
    ], key=itemgetter('name'))

    assert len(expected_funcs) == len(funcs), f"Wrong number of registered functions: {funcs}"

    for f, exp_f in zip(funcs, expected_funcs):
        for k in ['name']:
            assert getattr(f, k) == exp_f[k]

    #
    # Call should be idempotent
    #
    call_command('register_analysis_functions')

    funcs = AnalysisFunction.objects.all()
    assert len(expected_funcs) == len(funcs)


@pytest.mark.django_db
def test_default_function_kwargs():
    from django.core.management import call_command

    call_command('register_analysis_functions')

    func = AnalysisFunction.objects.get(name='Contact mechanics')

    expected_kwargs = dict(
        substrate_str='nonperiodic',
        hardness=None,
        nsteps=10,
        pressures=None,
        maxiter=100,
    )
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





