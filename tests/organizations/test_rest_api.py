import pytest
from rest_framework.reverse import reverse

from topobank.organizations.models import Organization
from topobank.testing.factories import OrganizationFactory


@pytest.mark.django_db
def test_create_organization(api_client, user_alice, user_staff):
    organization_dict = {"name": "Blofield, Inc."}

    # Create organization as anonymous user should fail
    response = api_client.post(
        reverse("organizations:organization-v1-list"),
        data=organization_dict,
        format="json",
    )
    # FIXME: Should be 401 Unauthorized
    assert response.status_code == 403, response.content

    assert Organization.objects.count() == 0

    # Create as user alice should also fail
    api_client.force_authenticate(user_alice)
    response = api_client.post(
        reverse("organizations:organization-v1-list"),
        data=organization_dict,
        format="json",
    )
    assert response.status_code == 403, response.content

    assert Organization.objects.count() == 0

    # Create as staff user should succeed
    api_client.force_authenticate(user_staff)
    response = api_client.post(
        reverse("organizations:organization-v1-list"),
        data=organization_dict,
        format="json",
    )
    assert response.status_code == 201, response.content

    assert Organization.objects.count() == 1

    # Create organization with same name should fail
    response = api_client.post(
        reverse("organizations:organization-v1-list"),
        data=organization_dict,
        format="json",
    )
    assert response.status_code == 400, response.content

    assert Organization.objects.count() == 1

    # Create organization without name should fail
    del organization_dict["name"]
    response = api_client.post(
        reverse("organizations:organization-v1-list"),
        data=organization_dict,
        format="json",
    )
    assert response.status_code == 400, response.content

    assert Organization.objects.count() == 1


@pytest.mark.django_db
def test_list_organizations(api_client, user_alice, user_bob, user_staff):
    # Searching for a user as the anonymous user should not be allowed
    response = api_client.get(reverse("organizations:organization-v1-list"))
    # FIXME: Should be 401 Unauthorized
    assert response.status_code == 403, response.content

    # Listing when logged in should yield the organization of the user
    api_client.force_authenticate(user_alice)
    response = api_client.get(reverse("organizations:organization-v1-list"))
    assert response.status_code == 200, response.content
    # List is now paginated. Check results in 'results' key, or count in 'count' key
    assert response.data["count"] == 0  # No organization assigned to alice

    org1 = OrganizationFactory()
    user_alice.groups.add(org1.group)
    response = api_client.get(reverse("organizations:organization-v1-list"))
    assert response.status_code == 200, response.content
    assert response.data["count"] == 1  # Alice has an organization now
    assert response.data["results"][0]["name"] == org1.name

    org2 = OrganizationFactory()
    user_bob.groups.add(org2.group)
    response = api_client.get(reverse("organizations:organization-v1-list"))
    assert response.status_code == 200, response.content
    assert response.data["count"] == 1  # Alice can only see her own organization
    assert response.data["results"][0]["name"] == org1.name

    # Login as bob and see whether he sees organization 2
    api_client.force_authenticate(user_bob)
    response = api_client.get(reverse("organizations:organization-v1-list"))
    assert response.status_code == 200, response.content
    assert response.data["count"] == 1  # Bob can only see his own organization
    assert response.data["results"][0]["name"] == org2.name

    # Login as staff and see all organizations
    api_client.force_authenticate(user_staff)
    response = api_client.get(reverse("organizations:organization-v1-list"))
    assert response.status_code == 200, response.content
    assert response.data["count"] == 2  # Staff can see all organizations
    assert {response.data["results"][0]["name"], response.data["results"][1]["name"]} == {
        org1.name,
        org2.name,
    }


@pytest.mark.django_db
def test_patch_organizations(api_client, user_alice, user_staff):
    org = OrganizationFactory()
    org.add(user_alice)
    org_data = {"name": "My new fancy name"}

    # Anonymous user cannot change the organization
    response = api_client.patch(
        reverse("organizations:organization-v1-detail", kwargs={"pk": org.id}),
        data=org_data,
    )
    assert response.status_code == 403, response.content

    # Alice cannot change the organization
    api_client.force_authenticate(user_alice)
    response = api_client.patch(
        reverse("organizations:organization-v1-detail", kwargs={"pk": org.id}),
        data=org_data,
    )
    assert response.status_code == 403, response.content

    # Staff can change the organization
    api_client.force_authenticate(user_staff)
    response = api_client.patch(
        reverse("organizations:organization-v1-detail", kwargs={"pk": org.id}),
        data=org_data,
    )
    assert response.status_code == 200, response.content

    # Alice can get the new name
    api_client.force_authenticate(user_alice)
    response = api_client.get(
        reverse("organizations:organization-v1-detail", kwargs={"pk": org.id})
    )
    assert response.status_code == 200, response.content
    assert response.data["name"] == org_data["name"]


@pytest.mark.django_db
def test_add_remove_users(api_client, user_alice, user_staff):
    org = OrganizationFactory()
    data_dict = {
        "user": reverse(
            "users:user-v1-detail", kwargs={"pk": user_alice.id}
        )
    }

    # Anonymous user cannot add users
    response = api_client.post(
        reverse("organizations:add-user-v1", kwargs={"pk": org.id}),
        data=data_dict,
    )
    assert response.status_code == 403, response.content
    assert user_alice.groups.count() == 0

    # Alice cannot add users
    api_client.force_authenticate(user_alice)
    response = api_client.post(
        reverse("organizations:add-user-v1", kwargs={"pk": org.id}),
        data=data_dict,
    )
    assert response.status_code == 403, response.content
    assert user_alice.groups.count() == 0

    # Staff can add users
    api_client.force_authenticate(user_staff)
    response = api_client.post(
        reverse("organizations:add-user-v1", kwargs={"pk": org.id}),
        data=data_dict,
    )
    assert response.status_code == 200, response.content
    assert user_alice.groups.count() == 1

    # Alice cannot remove users
    api_client.force_authenticate(user_alice)
    response = api_client.post(
        reverse("organizations:remove-user-v1", kwargs={"pk": org.id}),
        data=data_dict,
    )
    assert response.status_code == 403, response.content
    assert user_alice.groups.count() == 1

    # Staff can remove users
    api_client.force_authenticate(user_staff)
    response = api_client.post(
        reverse("organizations:remove-user-v1", kwargs={"pk": org.id}),
        data=data_dict,
    )
    assert response.status_code == 200, response.content
    assert user_alice.groups.count() == 0
