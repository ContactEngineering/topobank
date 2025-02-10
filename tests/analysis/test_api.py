from django.urls import reverse


def test_api():
    """Test API routes"""
    assert (
        reverse("analysis:card-series", kwargs=dict(workflow="my.function"))
        == "/analysis/api/card/series/my.function"
    )
    assert (
        reverse("analysis:configuration-detail", kwargs=dict(pk=123))
        == "/analysis/api/configuration/123/"
    )
    assert reverse("analysis:workflow-list") == "/analysis/api/workflow/"
    assert (
        reverse("analysis:workflow-detail", kwargs=dict(name="my.function"))
        == "/analysis/api/workflow/my.function/"
    )
    assert (
        reverse("analysis:result-detail", kwargs=dict(pk=123))
        == "/analysis/api/result/123/"
    )
