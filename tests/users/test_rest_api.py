import pytest
from rest_framework.reverse import reverse

from topobank.testing.factories import OrganizationFactory
from topobank.users.models import User


@pytest.mark.django_db
def test_create_user(api_client, user_alice, user_staff):
    user_dict = {
        "username": "frank",
        "name": "Frank Smith",
    }

    # Create user as anonymous user should fail
    response = api_client.post(
        reverse("users:user-api-list"), data=user_dict, format="json"
    )
    assert response.status_code == 403, response.content

    assert User.objects.count() == 3  # Anonymous, alice, staff

    # Create as user alice should also fail
    api_client.force_authenticate(user_alice)
    response = api_client.post(
        reverse("users:user-api-list"), data=user_dict, format="json"
    )
    assert response.status_code == 403, response.content

    assert User.objects.count() == 3  # Anonymous, alice, staff

    # Create as staff user should succeed
    api_client.force_authenticate(user_staff)
    response = api_client.post(
        reverse("users:user-api-list"), data=user_dict, format="json"
    )
    assert response.status_code == 201, response.content

    assert User.objects.count() == 4  # Anonymous, alice, staff, frank

    # Create user with same name should fail
    response = api_client.post(
        reverse("users:user-api-list"), data=user_dict, format="json"
    )
    assert response.status_code == 400, response.content

    assert User.objects.count() == 4  # Anonymous, alice, staff, frank

    # Create user without name should fail
    del user_dict["name"]
    response = api_client.post(
        reverse("users:user-api-list"), data=user_dict, format="json"
    )
    assert response.status_code == 400, response.content

    assert User.objects.count() == 4  # Anonymous, alice, staff, frank


@pytest.mark.django_db
def test_search_user(api_client, user_alice, user_bob, user_staff):
    # Searching for a user as the anonymous user should not be allowed
    response = api_client.get(f'{reverse("users:user-api-list")}?name=bob')
    assert response.status_code == 403, response.content

    # Searching for a user when logged in should yield the user
    api_client.force_authenticate(user_alice)
    response = api_client.get(f'{reverse("users:user-api-list")}?name=bob')
    assert response.status_code == 200, response.content
    assert len(response.data) == 1
    user = response.data[0]
    assert user["name"] == user_bob.name
    assert user["username"] == user_bob.username
    assert user["id"] == user_bob.id
    assert user["url"] == user_bob.get_absolute_url(response.wsgi_request)


@pytest.mark.django_db
def test_patch_user(api_client, user_alice, user_bob, user_staff):
    # Changing user information as the anonymous user should fail
    response = api_client.patch(
        reverse("users:user-api-detail", kwargs={"pk": user_alice.id}),
        data={"email": "alice@example.com"},
        format="json",
    )
    assert response.status_code == 403, response.content

    # Changing bob as user alice should fail with a 404 because alice cannot
    # see bob
    api_client.force_authenticate(user_alice)
    response = api_client.get(
        reverse("users:user-api-detail", kwargs={"pk": user_bob.id})
    )
    assert response.status_code == 404, response.content
    response = api_client.patch(
        reverse("users:user-api-detail", kwargs={"pk": user_bob.id}),
        data={"email": "bob@example.com"},
        format="json",
    )
    assert response.status_code == 404, response.content

    # We now add bob and alice to the same organization
    org = OrganizationFactory()
    org.add(user_alice)
    org.add(user_bob)

    # Changing bob as user alice should now fail with a 403 because alice
    # can see but not edit bob
    api_client.force_authenticate(user_alice)
    response = api_client.get(
        reverse("users:user-api-detail", kwargs={"pk": user_bob.id})
    )
    assert response.status_code == 200, response.content
    response = api_client.patch(
        reverse("users:user-api-detail", kwargs={"pk": user_bob.id}),
        data={"email": "bob@example.com"},
        format="json",
    )
    assert response.status_code == 403, response.content

    # But changing alice as user alice should work
    response = api_client.patch(
        reverse("users:user-api-detail", kwargs={"pk": user_alice.id}),
        data={"email": "alice@example.com"},
        format="json",
    )
    assert response.status_code == 200, response.content

    # Staff user can change all users
    api_client.force_authenticate(user_staff)
    response = api_client.patch(
        reverse("users:user-api-detail", kwargs={"pk": user_alice.id}),
        data={"email": "alice@staff.com"},
        format="json",
    )
    assert response.status_code == 200, response.content
    response = api_client.patch(
        reverse("users:user-api-detail", kwargs={"pk": user_bob.id}),
        data={"email": "bob@staff.com"},
        format="json",
    )
    assert response.status_code == 200, response.content
