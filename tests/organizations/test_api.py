from django.urls import reverse


def test_api():
    """Test API routes"""
    assert (
        reverse("organizations:organization-v1-list")
        == "/organizations/v1/organization/"
    )
    assert (
        reverse("organizations:organization-v1-detail", kwargs=dict(pk=123))
        == "/organizations/v1/organization/123/"
    )
