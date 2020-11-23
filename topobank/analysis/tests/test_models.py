import pytest
from operator import itemgetter
import datetime
from django.db.models.functions import Lower

from ..models import Analysis, AnalysisFunction
from topobank.manager.models import Topography
from topobank.manager.tests.utils import two_topos


@pytest.mark.django_db
def test_analysis_times(two_topos):

    import pickle

    analysis = Analysis.objects.create(
            topography=Topography.objects.first(),
            function=AnalysisFunction.objects.first(),
            task_state=Analysis.SUCCESS,
            kwargs=pickle.dumps({'bins':2, 'mode': 'test'}),
            start_time=datetime.datetime(2018,1,1,12),
            end_time=datetime.datetime(2018,1,1,13),
        )
    analysis.save()

    assert analysis.start_time == datetime.datetime(2018,1,1,12)
    assert analysis.end_time == datetime.datetime(2018, 1, 1, 13)
    assert analysis.duration() == datetime.timedelta(0, 3600)

    assert analysis.get_kwargs_display() == str({'bins':2, 'mode': 'test'})


# @pytest.mark.skip("Cannot run startup code which modifies the database so far.")
@pytest.mark.django_db
def test_autoload_analysis_functions():
    # TODO this test has a problem: It's not independent from the available functions

    from django.core.management import call_command

    call_command('register_analysis_functions')

    funcs = AnalysisFunction.objects.all().order_by('name')

    expected_funcs = sorted([
        dict(pyfunc='height_distribution', automatic=True, name='Height Distribution',),
        dict(pyfunc='slope_distribution', automatic=True, name='Slope Distribution'),
        dict(pyfunc='curvature_distribution', automatic=True, name='Curvature Distribution'),
        dict(pyfunc='power_spectrum', automatic=True, name='Power Spectrum'),
        dict(pyfunc='autocorrelation', automatic=True, name='Autocorrelation'),
        dict(pyfunc='variable_bandwidth', automatic=True, name='Variable Bandwidth'),
        dict(pyfunc='contact_mechanics', automatic=True, name='Contact Mechanics'),
        dict(pyfunc='rms_values', automatic=True, name='RMS Values'),
    ], key=itemgetter('name'))

    assert len(expected_funcs) == len(funcs)

    for f, exp_f in zip(funcs, expected_funcs):
        for k in ['pyfunc', 'automatic', 'name']:
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

    func = AnalysisFunction.objects.get(pyfunc='contact_mechanics')

    expected_kwargs = dict(
        substrate_str = None,
        hardness = None,
        nsteps = 10,
        pressures = None,
        maxiter = 100,
    )

    assert func.get_default_kwargs() == expected_kwargs


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
    # Lower: Just to have a defined order independent from database used

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





