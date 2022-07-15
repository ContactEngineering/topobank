import pytest

from topobank.analysis.models import AnalysisFunction


@pytest.mark.django_db
def test_autoload_analysis_functions():
    from django.core.management import call_command

    call_command('register_analysis_functions')

    # remember number of functions
    num_funcs = AnalysisFunction.objects.count()

    expected_funcs_names = sorted([
        'Height distribution',
        'Slope distribution',
        'Curvature distribution',
        'Power spectrum',
        'Autocorrelation',
        'Variable bandwidth',
        'Scale-dependent slope',
        'Scale-dependent curvature',
    ])

    assert len(expected_funcs_names) <= num_funcs

    available_funcs_names = AnalysisFunction.objects.values("name")

    for efn in expected_funcs_names:
        assert efn in available_funcs_names

    #
    # Call should be idempotent
    #
    call_command('register_analysis_functions')
    assert num_funcs == AnalysisFunction.objects.count()
