import pytest

from topobank.analysis.models import AnalysisFunction


@pytest.mark.django_db
def test_autoload_analysis_functions():
    # TODO this test has a problem: It's not independent from the available functions

    from django.core.management import call_command

    call_command('register_analysis_functions')

    available_funcs_names = list(x[0] for x in AnalysisFunction.objects.values_list("name"))

    expected_funcs_names = sorted([
        'Height distribution',
        'Slope distribution',
        'Curvature distribution',
        'Power spectrum',
        'Autocorrelation',
        'Variable bandwidth',
        'Roughness parameters',
        'Scale-dependent slope',
        'Scale-dependent curvature',
    ])

    assert len(expected_funcs_names) <= len(available_funcs_names)

    for efn in expected_funcs_names:
        assert efn in available_funcs_names

    #
    # Call should be idempotent
    #
    call_command('register_analysis_functions')
    assert len(available_funcs_names) == AnalysisFunction.objects.count()
