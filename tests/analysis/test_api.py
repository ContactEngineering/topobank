from django.urls import reverse


def test_v1_card_series_route():
    """Test v1 card series API route"""
    assert (
        reverse("analysis:card-series", kwargs=dict(workflow="my.function"))
        == "/analysis/api/card/series/my.function"
    )


def test_v1_configuration_route():
    """Test v1 configuration API route"""
    assert (
        reverse("analysis:configuration-detail", kwargs=dict(pk=123))
        == "/analysis/api/configuration/123/"
    )


def test_v1_workflow_routes():
    """Test v1 workflow API routes"""
    assert reverse("analysis:workflow-list") == "/analysis/api/workflow/"
    assert (
        reverse("analysis:workflow-detail", kwargs=dict(name="my.function"))
        == "/analysis/api/workflow/my.function/"
    )


def test_v1_result_route():
    """Test v1 result API route"""
    assert (
        reverse("analysis:result-detail", kwargs=dict(pk=123))
        == "/analysis/api/result/123/"
    )
