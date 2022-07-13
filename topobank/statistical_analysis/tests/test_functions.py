import pytest

from operator import itemgetter

from topobank.analysis.models import AnalysisFunction

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
        # dict(name='Contact mechanics'),
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
