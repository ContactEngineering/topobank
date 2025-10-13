from rest_framework.reverse import reverse


def test_api():
    """Test API routes"""
    assert (
        reverse("authorization:permission-set-v1-detail", kwargs=dict(pk=123))
        == "/authorization/v1/permission-set/123/"
    )
    assert (
        reverse("authorization:grant-user-access-v2", kwargs=dict(pk=123))
        == "/authorization/v1/grant-user-access/123/"
    )
    assert (
        reverse("authorization:revoke-user-access-v2", kwargs=dict(pk=123))
        == "/authorization/v1/revoke-user-access/123/"
    )
    assert (
        reverse("authorization:grant-organization-access-v2", kwargs=dict(pk=123))
        == "/authorization/v1/grant-organization-access/123/"
    )
    assert (
        reverse("authorization:revoke-organization-access-v2", kwargs=dict(pk=123))
        == "/authorization/v1/revoke-organization-access/123/"
    )
