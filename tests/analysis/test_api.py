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


def test_v2_result_routes():
    """Test v2 result API routes"""
    assert (
        reverse("analysis:result-v2-detail", kwargs=dict(pk=123))
        == "/analysis/v2/results/123/"
    )
    assert (
        reverse("analysis:result-v2-list") == "/analysis/v2/results/"
    )
    assert (
        reverse("analysis:result-v2-dependency", kwargs=dict(pk=123))
        == "/analysis/v2/results/123/dependencies/"
    )
    assert (
        reverse("analysis:result-v2-run", kwargs=dict(pk=123))
        == "/analysis/v2/results/123/run/"
    )


def test_v2_configuration_route():
    """Test v2 configuration API route"""
    assert (
        reverse("analysis:configuration-v2-detail", kwargs=dict(pk=123))
        == "/analysis/v2/configurations/123/"
    )


def test_v2_workflow_routes():
    """Test v2 workflow API routes"""
    assert (
        reverse("analysis:workflow-v2-detail", kwargs=dict(pk=123))
        == "/analysis/v2/workflows/123/"
    )
    assert (
        reverse("analysis:workflow-v2-list") == "/analysis/v2/workflows/"
    )
