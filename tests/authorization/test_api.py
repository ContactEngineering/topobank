from rest_framework.reverse import reverse


def test_api():
    """Test API routes"""
    assert (
        reverse("authorization:permission-set-v1-detail", kwargs=dict(pk=123))
        == "/authorization/v1/permission-set/123/"
    )
    assert (
        reverse("authorization:add-user-v1", kwargs=dict(pk=123))
        == "/authorization/v1/add-user/123/"
    )
    assert (
        reverse("authorization:remove-user-v1", kwargs=dict(pk=123))
        == "/authorization/v1/remove-user/123/"
    )
    assert (
        reverse("authorization:add-organization-v1", kwargs=dict(pk=123))
        == "/authorization/v1/add-organization/123/"
    )
    assert (
        reverse("authorization:remove-organization-v1", kwargs=dict(pk=123))
        == "/authorization/v1/remove-organization/123/"
    )
