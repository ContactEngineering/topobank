from django.urls import reverse


def test_api():
    """Test API routes"""
    assert reverse("users:user-v1-list") == "/users/v1/user/"
    assert (
        reverse("users:user-v1-detail", kwargs=dict(pk=123)) == "/users/v1/user/123/"
    )
