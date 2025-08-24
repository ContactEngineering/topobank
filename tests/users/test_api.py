from django.urls import reverse


def test_api():
    """Test API routes"""
    assert reverse("users:user-api-list") == "/users/api/user/"
    assert (
        reverse("users:user-api-detail", kwargs=dict(pk=123)) == "/users/api/user/123/"
    )
