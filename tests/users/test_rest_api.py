import pytest
from rest_framework.reverse import reverse

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
