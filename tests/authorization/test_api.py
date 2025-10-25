from rest_framework.reverse import reverse


def test_api():
    """Test API routes"""
    assert (
        reverse("authorization:permission-set-v2-detail", kwargs=dict(id=123))
        == "/authorization/v2/permission-set/123/"
    )
    assert (
        reverse("authorization:grant-user-access-v2", kwargs=dict(id=123))
        == "/authorization/v2/grant-user-access/123/"
    )
    assert (
        reverse("authorization:revoke-user-access-v2", kwargs=dict(id=123))
        == "/authorization/v2/revoke-user-access/123/"
    )
    assert (
        reverse("authorization:grant-organization-access-v2", kwargs=dict(id=123))
        == "/authorization/v2/grant-organization-access/123/"
    )
    assert (
        reverse("authorization:revoke-organization-access-v2", kwargs=dict(id=123))
        == "/authorization/v2/revoke-organization-access/123/"
    )
