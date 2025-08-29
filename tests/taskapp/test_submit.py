import pydantic
import pytest

from topobank.analysis.models import WorkflowResult
from topobank.testing.factories import Topography1DFactory, TopographyAnalysisFactory


@pytest.mark.django_db
def test_request_analysis(mocker, test_analysis_function):
    """Make sure analysis objects were created with correct parameters"""

    mocker.patch(
        "topobank.taskapp.utils.run_task"
    )  # we don't want to calculate anything

    topo = Topography1DFactory()
    user = topo.creator

    # just an abbreviation
    def assert_correct_args(analysis, expected_kwargs):
        kwargs = analysis.kwargs
        assert kwargs == expected_kwargs
        assert analysis.has_permission(user, "view")  # make sure the user has been set

    # test case 1
    analysis = test_analysis_function.submit(user, topo, dict(a=13, b="24"))
    assert_correct_args(analysis, dict(a=13, b="24"))

    # test case 2
    analysis = test_analysis_function.submit(user, topo, dict(a=1, b="2"))
    assert_correct_args(analysis, dict(a=1, b="2"))

    # test case 3
    analysis = test_analysis_function.submit(user, topo, dict(a=2, b="1"))
    assert_correct_args(analysis, dict(a=2, b="1"))

    # test case 4
    with pytest.raises(pydantic.ValidationError):
        test_analysis_function.submit(user, topo, dict(a=1, c=24))

    # test case 4
    with pytest.raises(pydantic.ValidationError):
        test_analysis_function.submit(user, topo, dict(a=1, b=2))


@pytest.mark.django_db
def test_different_kwargs(mocker, test_analysis_function):
    """
    When requesting an analysis with new arguments, the old analyses should still exist
    (at the moment, maybe delete later analyses without user),
    but only the latest one should be marked as "used" by the user
    """
    m = mocker.patch("topobank.analysis.models.Workflow.eval")
    m.return_value = {"result1": 1, "result2": 2}

    topo = Topography1DFactory()
    user = topo.creator

    a1 = TopographyAnalysisFactory(
        subject_topography=topo,
        function=test_analysis_function,
        kwargs=dict(a=9, b=19),
        user=user,
    )
    a2 = TopographyAnalysisFactory(
        subject_topography=topo,
        function=test_analysis_function,
        kwargs=dict(a=29, b=39),
        user=user,
    )

    a3 = test_analysis_function.submit(user, topo, {"a": 1, "b": "2"})

    #
    # Now there are three analyses for af+topo
    #
    assert (
        WorkflowResult.objects.filter(
            subject_dispatch__topography=topo, function=test_analysis_function
        ).count()
        == 3
    )

    #
    # Only one analysis is marked for user 'user'
    #
    analyses = WorkflowResult.objects.filter(
        subject_dispatch__topography=topo,
        function=test_analysis_function,
        permissions__user_permissions__user=user,
    )

    assert len(analyses) == 3

    assert a1 in analyses
    assert a2 in analyses
    assert a3 in analyses
