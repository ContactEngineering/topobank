import pytest
from rest_framework.reverse import reverse

from topobank.organizations.models import Organization


@pytest.mark.django_db
def test_create_organization(api_client, user_alice, user_staff):
    organization_dict = {
        "name": "Blofield, Inc."
    }

    # Create organization as anonymous user should fail
    response = api_client.post(
        reverse("organizations:organization-api-list"), data=organization_dict, format="json"
    )
    assert response.status_code == 403, response.content

    assert Organization.objects.count() == 0

    # Create as user alice should also fail
    api_client.force_authenticate(user_alice)
    response = api_client.post(
        reverse("organizations:organization-api-list"), data=organization_dict, format="json"
    )
    assert response.status_code == 403, response.content

    assert Organization.objects.count() == 0

    # Create as staff user should succeed
    api_client.force_authenticate(user_staff)
    response = api_client.post(
        reverse("organizations:organization-api-list"), data=organization_dict, format="json"
    )
    assert response.status_code == 201, response.content

    assert Organization.objects.count() == 1

    # Create organization with same name should fail
    response = api_client.post(
        reverse("organizations:organization-api-list"), data=organization_dict, format="json"
    )
    assert response.status_code == 400, response.content

    assert Organization.objects.count() == 1

    # Create organization without name should fail
    del organization_dict["name"]
    response = api_client.post(
        reverse("organizations:organization-api-list"), data=organization_dict, format="json"
    )
    assert response.status_code == 400, response.content

    assert Organization.objects.count() == 1


@pytest.mark.django_db
def test_list_organizations(api_client, user_alice, user_bob, user_staff):
    # Searching for a user as the anonymous user should not be allowed
    response = api_client.get(reverse("organizations:organization-api-list"))
    assert response.status_code == 403, response.content

    # Listing when logged in should yield the organization of the user
    api_client.force_authenticate(user_alice)
    response = api_client.get(reverse("organizations:organization-api-list"))
    assert response.status_code == 200, response.content
    assert len(response.data) == 0  # No organization assigned to alice
