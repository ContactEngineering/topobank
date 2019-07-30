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
def test_configuration(settings):

    settings.TRACKED_PACKAGES = [
        ('PyCo', 'PyCo.__version__'),
        ('topobank', 'topobank.__version__'),
        ('numpy', 'numpy.version.full_version')
    ]

    from topobank.taskapp.tasks import current_configuration

    config = current_configuration()

    versions = config.versions.order_by(Lower('dependency__import_name'))
    # Lower: Just to have a defined order independent from database used

    assert len(versions) == 3

    v0, v1, v2 = versions

    import numpy
    assert v0.dependency.import_name == 'numpy'
    assert f"{v0.major}.{v0.minor}.{v0.micro}" == numpy.version.full_version

    import PyCo
    assert v1.dependency.import_name == 'PyCo'
    assert f"{v1.major}.{v1.minor}.{v1.micro}" == PyCo.__version__

    import topobank
    assert v2.dependency.import_name == 'topobank'
    assert f"{v2.major}.{v2.minor}.{v2.micro}" == topobank.__version__


