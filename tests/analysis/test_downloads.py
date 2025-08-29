"""
Test of downloads module.
"""

import pytest
from django.shortcuts import reverse

from topobank.analysis.downloads import download_plot_analyses_to_txt
from topobank.testing.factories import (
    FailedTopographyAnalysisFactory,
    TopographyAnalysisFactory,
    Workflow,
)
from topobank.testing.utils import assert_in_content


@pytest.mark.django_db
def test_download_plot_analyses_to_txt(rf):
    func = Workflow.objects.get(name="topobank.testing.test")
    analysis1 = TopographyAnalysisFactory(function=func)
    analysis2 = FailedTopographyAnalysisFactory(function=func)
    request = rf.get(
        reverse(
            "analysis:download",
            kwargs=dict(ids=f"{analysis1.id},{analysis2.id}", file_format="txt"),
        )
    )

    response = download_plot_analyses_to_txt(request, [analysis1, analysis2])

    assert_in_content(response, "Fibonacci")
    assert_in_content(
        response,
        "1.000000000000000000e+00 0.000000000000000000e+00 0.000000000000000000e+00",
    )
    assert_in_content(
        response,
        "8.000000000000000000e+00 1.300000000000000000e+01 0.000000000000000000e+00",
    )

    assert_in_content(response, "This analysis reported an error during execution")


@pytest.mark.parametrize("user_has_plugin", [False, True])
@pytest.mark.django_db
def test_download_view_permission_for_function_from_plugin(
    mocker, api_client, user_has_plugin, handle_usage_statistics
):
    """Simple test, whether analyses which should not be visible lead to an error during download."""
    func = Workflow.objects.get(name="topobank.testing.test")

    analysis = TopographyAnalysisFactory(function=func)

    m = mocker.patch(
        "topobank.analysis.workflows.WorkflowImplementation.has_permission"
    )
    m.return_value = user_has_plugin

    api_client.force_login(analysis.subject.creator)

    response = api_client.get(
        reverse(
            "analysis:download", kwargs=dict(ids=str(analysis.id), file_format="txt")
        )
    )
    if user_has_plugin:
        assert response.status_code == 200, response.reason_phrase
    else:
        assert response.status_code == 403, response.reason_phrase
