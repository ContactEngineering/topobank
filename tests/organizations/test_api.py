from django.urls import reverse


def test_api():
    """Test API routes"""
    assert (
        reverse("organizations:organization-api-list")
        == "/organizations/api/organization/"
    )
    assert (
        reverse("organizations:organization-api-detail", kwargs=dict(pk=123))
        == "/organizations/api/organization/123/"
    )
