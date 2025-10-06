import pytest
from rest_framework.reverse import reverse


@pytest.mark.django_db
def test_add_remove_user(api_client, one_line_scan, user_alice):
    surface = one_line_scan.surface

    # The creator of the surface can access it
    api_client.force_authenticate(surface.creator)
    response = api_client.get(surface.get_absolute_url())
    assert response.status_code == 200, response.content

    # Alice cannot access the surface
    api_client.force_authenticate(user_alice)
    response = api_client.get(surface.get_absolute_url())
    assert response.status_code == 404, response.content

    # Alice cannot give itself access to the surface
    response = api_client.post(
        reverse("authorization:add-user-v1", kwargs={"pk": surface.permissions.id}),
        data={"user": user_alice.get_absolute_url(), "allow": "view"},
    )
    assert response.status_code == 404, response.content

    # But the owner of the surface can give access to Alice
    api_client.force_authenticate(surface.creator)
    response = api_client.post(
        reverse("authorization:add-user-v1", kwargs={"pk": surface.permissions.id}),
        data={"user": user_alice.get_absolute_url(), "allow": "view"},
    )
    assert response.status_code == 201, response.content

    # Alice can now access the surface
    api_client.force_authenticate(user_alice)
    response = api_client.get(surface.get_absolute_url())
    assert response.status_code == 200, response.content

    # Alice cannot revoke access to the surface from itself
    response = api_client.post(
        reverse("authorization:remove-user-v1", kwargs={"pk": surface.permissions.id}),
        data={"user": user_alice.get_absolute_url()},
    )
    assert response.status_code == 403, response.content

    # But the owner of the surface can revoke access to Alice
    api_client.force_authenticate(surface.creator)
    response = api_client.post(
        reverse("authorization:remove-user-v1", kwargs={"pk": surface.permissions.id}),
        data={"user": user_alice.get_absolute_url()},
    )
    assert response.status_code == 204, response.content

    # Alice can no longer access the surface
    api_client.force_authenticate(user_alice)
    response = api_client.get(surface.get_absolute_url())
    assert response.status_code == 404, response.content


@pytest.mark.django_db
def test_add_remove_organization(api_client, one_line_scan, user_alice, org_blofield):
    surface = one_line_scan.surface

    # We add Alice to the Blofield organization
    org_blofield.add(user_alice)

    # The creator of the surface can access it
    api_client.force_authenticate(surface.creator)
    response = api_client.get(surface.get_absolute_url())
    assert response.status_code == 200, response.content

    # Alice cannot access the surface
    api_client.force_authenticate(user_alice)
    response = api_client.get(surface.get_absolute_url())
    assert response.status_code == 404, response.content

    # Alice cannot give itself access to the surface
    response = api_client.post(
        reverse(
            "authorization:add-organization-v1", kwargs={"pk": surface.permissions.id}
        ),
        data={"organization": org_blofield.get_absolute_url(), "allow": "view"},
    )
    assert response.status_code == 404, response.content

    # But the owner of the surface can give access to Alice through the Blofield organization
    api_client.force_authenticate(surface.creator)
    response = api_client.post(
        reverse(
            "authorization:add-organization-v1", kwargs={"pk": surface.permissions.id}
        ),
        data={"organization": org_blofield.get_absolute_url(), "allow": "view"},
    )
    assert response.status_code == 201, response.content

    # Alice can now access the surface
    api_client.force_authenticate(user_alice)
    response = api_client.get(surface.get_absolute_url())
    assert response.status_code == 200, response.content

    # Alice cannot revoke access to the surface from itself
    response = api_client.post(
        reverse(
            "authorization:remove-organization-v1",
            kwargs={"pk": surface.permissions.id},
        ),
        data={"organization": org_blofield.get_absolute_url()},
    )
    assert response.status_code == 403, response.content

    # But the owner of the surface can revoke access to Alice
    api_client.force_authenticate(surface.creator)
    response = api_client.post(
        reverse(
            "authorization:remove-organization-v1",
            kwargs={"pk": surface.permissions.id},
        ),
        data={"organization": org_blofield.get_absolute_url()},
    )
    assert response.status_code == 204, response.content

    # Alice can no longer access the surface
    api_client.force_authenticate(user_alice)
    response = api_client.get(surface.get_absolute_url())
    assert response.status_code == 404, response.content
