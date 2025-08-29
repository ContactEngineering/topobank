import pytest

from topobank.analysis.models import WorkflowResult
from topobank.analysis.tasks import get_current_configuration, perform_analysis
from topobank.manager.models import Topography
from topobank.testing.factories import TopographyAnalysisFactory


@pytest.mark.django_db
def test_perform_analysis(
    two_topos, test_analysis_function, settings, handle_usage_statistics
):
    topo = Topography.objects.first()  # doesn't matter

    func_kwargs = dict(a=1, b="hamming")

    analysis = TopographyAnalysisFactory.create(
        subject_topography=topo,
        function=test_analysis_function,
        kwargs=func_kwargs,
        result=None,
        task_state=WorkflowResult.PENDING
    )
    analysis.save()

    perform_analysis(analysis.id, False)

    # now check result
    analysis = WorkflowResult.objects.get(id=analysis.id)
    assert analysis.result["comment"] == "Arguments: a is 1 and b is hamming"

    # Analysis object should remember the current configuration
    first_config = get_current_configuration()
    assert analysis.configuration == first_config

    #
    # No let's change the version of SurfaceTopography
    #
    settings.TRACKED_DEPENDENCIES = [
        (
            "SurfaceTopography",
            '"0.89.1"',
            "MIT",
            "abc",
        ),  # this version does not exist, so should be unknown here
        ("topobank", "topobank.__version__", "MIT", "def"),
        ("numpy", "numpy.version.full_version", "BSD 3-Clause", "ghi"),
    ]

    topo2 = Topography.objects.last()
    analysis2 = TopographyAnalysisFactory.create(
        subject_topography=topo2,
        function=test_analysis_function,
        kwargs=func_kwargs,
        result=None,
        task_state=WorkflowResult.PENDING
    )

    analysis2.save()
    perform_analysis(analysis2.id, False)

    analysis2 = WorkflowResult.objects.get(id=analysis2.id)

    # configuration should have been changed
    assert analysis2.configuration is not None
    assert analysis2.configuration != first_config

    new_st_version = analysis2.configuration.versions.get(
        dependency__import_name="SurfaceTopography"
    )

    assert new_st_version.major == 0
    assert new_st_version.minor == 89
    assert new_st_version.micro == 1

    # other versions stay the same
    numpy_version = analysis2.configuration.versions.get(
        dependency__import_name="numpy"
    )
    assert numpy_version == first_config.versions.get(dependency__import_name="numpy")

    topobank_version = analysis2.configuration.versions.get(
        dependency__import_name="topobank"
    )
    assert topobank_version == first_config.versions.get(
        dependency__import_name="topobank"
    )
