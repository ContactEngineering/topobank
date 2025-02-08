from django.urls import reverse


def test_api():
    """Test API routes"""
    assert (
        reverse("analysis:card-series", kwargs=dict(function_name="my.function"))
        == "/analysis/api/card/series/my.function"
    )
    assert (
        reverse("analysis:configuration-detail", kwargs=dict(pk=123))
        == "/analysis/api/configuration/123/"
    )
    assert reverse("analysis:function-list") == "/analysis/api/function/"
    assert (
        reverse("analysis:function-detail", kwargs=dict(name="my.function"))
        == "/analysis/api/function/my.function/"
    )
    assert (
        reverse("analysis:result-detail", kwargs=dict(pk=123))
        == "/analysis/api/result/123/"
    )
