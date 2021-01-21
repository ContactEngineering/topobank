import pytest
import pickle

from ..tasks import perform_analysis, current_configuration

from topobank.analysis.models import Analysis
from topobank.analysis.models import AnalysisFunction
from topobank.manager.models import Topography
from topobank.manager.tests.utils import two_topos


@pytest.mark.django_db
def test_perform_analysis(mocker, two_topos, settings):

    def my_func(topography, a=0, b=1, bins=15, window='hann', progress_recorder=None, storage_prefix=None):
        return {
            'topotype': type(topography.topography()),
            'x': (a+b)*bins,
            's': window
        }

    m = mocker.patch('topobank.analysis.models.AnalysisFunctionImplementation.python_function',
                     new_callable=mocker.PropertyMock)
    m.return_value = my_func

    af = AnalysisFunction.objects.first()  # doesn't matter
    topo = Topography.objects.first()  # doesn't matter

    func_kwargs = dict(a=1,
                       b=2,
                       bins=10,
                       window="hamming")

    analysis = Analysis.objects.create(
                                topography=topo,
                                function=af,
                                kwargs=pickle.dumps(func_kwargs))
    analysis.save()

    settings.CELERY_TASK_ALWAYS_EAGER = True  # perform tasks locally

    # with mocker.patch('django.conf.settings.CELERY_ALWAYS_EAGER', True, create=True):
    perform_analysis(analysis.id)

    # now check result
    analysis = Analysis.objects.get(id=analysis.id)
    assert pickle.loads(analysis.result) == {
        'topotype': type(topo.topography()),
        'x': 30,
        's': 'hamming'
    }

    # Analysis object should remember current configuration
    first_config = current_configuration()
    assert analysis.configuration == first_config

    #
    # No let's change the version of SurfaceTopography
    #
    settings.TRACKED_DEPENDENCIES = [
        ('SurfaceTopography', '"0.89.1"'),      # this version does not exist, so should be unknown here
        ('topobank', 'topobank.__version__'),
        ('numpy', 'numpy.version.full_version')
    ]

    topo2 = Topography.objects.last()
    analysis2 = Analysis.objects.create(
        topography=topo2,
        function=af,
        kwargs=pickle.dumps(func_kwargs))

    analysis2.save()
    perform_analysis(analysis2.id)

    analysis2 = Analysis.objects.get(id=analysis2.id)

    # configuration should have been changed
    assert analysis2.configuration is not None
    assert analysis2.configuration != first_config

    new_st_version = analysis2.configuration.versions.get(dependency__import_name='SurfaceTopography')

    assert new_st_version.major == 0
    assert new_st_version.minor == 89
    assert new_st_version.micro == 1

    # other versions stay the same
    numpy_version = analysis2.configuration.versions.get(dependency__import_name='numpy')
    assert numpy_version == first_config.versions.get(dependency__import_name='numpy')

    topobank_version = analysis2.configuration.versions.get(dependency__import_name='topobank')
    assert topobank_version == first_config.versions.get(dependency__import_name='topobank')

