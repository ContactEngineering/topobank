import pytest
from rest_framework.reverse import reverse

from topobank.manager.custodian import periodic_cleanup
from topobank.manager.models import Topography
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
        reverse("users:user-v1-list"), data=user_dict, format="json"
    )
    assert response.status_code == 403, response.content

    assert User.objects.count() == 3  # Anonymous, alice, staff

    # Create as user alice should also fail
    api_client.force_authenticate(user_alice)
    response = api_client.post(
        reverse("users:user-v1-list"), data=user_dict, format="json"
    )
    assert response.status_code == 403, response.content

    assert User.objects.count() == 3  # Anonymous, alice, staff

    # Create as staff user should succeed
    api_client.force_authenticate(user_staff)
    response = api_client.post(
        reverse("users:user-v1-list"), data=user_dict, format="json"
    )
    assert response.status_code == 201, response.content

    assert User.objects.count() == 4  # Anonymous, alice, staff, frank

    # Create user with same name should fail
    response = api_client.post(
        reverse("users:user-v1-list"), data=user_dict, format="json"
    )
    assert response.status_code == 400, response.content

    assert User.objects.count() == 4  # Anonymous, alice, staff, frank

    # Create user without name should fail
    del user_dict["name"]
    response = api_client.post(
        reverse("users:user-v1-list"), data=user_dict, format="json"
    )
    assert response.status_code == 400, response.content

    assert User.objects.count() == 4  # Anonymous, alice, staff, frank


@pytest.mark.django_db
def test_search_user(api_client, user_alice, user_bob, user_staff):
    # Searching for a user as the anonymous user should not be allowed
    response = api_client.get(f'{reverse("users:user-v1-list")}?name=bob')
    assert response.status_code == 403, response.content

    # Searching for a user when logged in should yields nothing if the users
    # are not in the same organization
    api_client.force_authenticate(user_alice)
    response = api_client.get(f'{reverse("users:user-v1-list")}?name=bob')
    assert response.status_code == 200, response.content
    assert len(response.data) == 0

    # Create organizations and enroll alice and bob
    org = OrganizationFactory()
    org.add(user_alice)
    org.add(user_bob)

    # Now alice can find bob
    response = api_client.get(f'{reverse("users:user-v1-list")}?name=bob')
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
        reverse("users:user-v1-detail", kwargs={"pk": user_alice.id}),
        data={"email": "alice@example.com"},
        format="json",
    )
    assert response.status_code == 403, response.content

    # Changing bob as user alice should fail with a 404 because alice cannot
    # see bob
    api_client.force_authenticate(user_alice)
    response = api_client.get(
        reverse("users:user-v1-detail", kwargs={"pk": user_bob.id})
    )
    assert response.status_code == 404, response.content
    response = api_client.patch(
        reverse("users:user-v1-detail", kwargs={"pk": user_bob.id}),
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
        reverse("users:user-v1-detail", kwargs={"pk": user_bob.id})
    )
    assert response.status_code == 200, response.content
    response = api_client.patch(
        reverse("users:user-v1-detail", kwargs={"pk": user_bob.id}),
        data={"email": "bob@example.com"},
        format="json",
    )
    assert response.status_code == 403, response.content

    # But changing alice as user alice should work
    response = api_client.patch(
        reverse("users:user-v1-detail", kwargs={"pk": user_alice.id}),
        data={"email": "alice@example.com"},
        format="json",
    )
    assert response.status_code == 200, response.content

    # Staff user can change all users
    api_client.force_authenticate(user_staff)
    response = api_client.patch(
        reverse("users:user-v1-detail", kwargs={"pk": user_alice.id}),
        data={"email": "alice@staff.com"},
        format="json",
    )
    assert response.status_code == 200, response.content
    response = api_client.patch(
        reverse("users:user-v1-detail", kwargs={"pk": user_bob.id}),
        data={"email": "bob@staff.com"},
        format="json",
    )
    assert response.status_code == 200, response.content


@pytest.mark.django_db
def test_delete_user(api_client, one_line_scan, user_alice, user_staff):
    user_line_scan = one_line_scan.created_by
    org = OrganizationFactory()
    one_line_scan.surface.owned_by = org
    one_line_scan.surface.save(update_fields=["owned_by"])

    # Deleting a user information as the anonymous user should fail
    response = api_client.delete(
        reverse("users:user-v1-detail", kwargs={"pk": user_alice.id})
    )
    assert response.status_code == 403, response.content

    # We now add bob and alice to the same organization
    org.add(user_alice)
    org.add(user_line_scan)

    # Deleting bob as user alice should fail because alice cannot delete
    # or edit bob
    api_client.force_authenticate(user_alice)
    response = api_client.delete(
        reverse("users:user-v1-detail", kwargs={"pk": user_line_scan.id})
    )
    assert response.status_code == 403, response.content

    # Staff user can delete user
    api_client.force_authenticate(user_staff)
    response = api_client.delete(
        reverse("users:user-v1-detail", kwargs={"pk": user_line_scan.id})
    )
    assert response.status_code == 204, response.content

    # This should succeed, line scan still exists
    topo = Topography.objects.get(id=one_line_scan.id)
    assert topo.surface.created_by is None

    # Run custodian
    periodic_cleanup()

    # This should succeed, line scan still exists because it has an owner
    topo = Topography.objects.get(id=one_line_scan.id)
    assert topo.surface.created_by is None

    # Remove owner and run custodian
    topo.surface.owned_by = None
    topo.surface.save(update_fields=["owned_by"])
    periodic_cleanup()

    # Line scan should have been deleted
    with pytest.raises(Topography.DoesNotExist):
        Topography.objects.get(id=one_line_scan.id)


@pytest.mark.django_db
def test_add_remove_organization(api_client, user_alice, user_staff):
    org = OrganizationFactory()
    data_dict = {
        "organization": reverse(
            "organizations:organization-v1-detail", kwargs={"pk": org.id}
        )
    }

    # Anonymous user cannot add organizations
    response = api_client.post(
        reverse("users:add-organization-v1", kwargs={"pk": user_alice.id}),
        data=data_dict,
    )
    assert response.status_code == 403, response.content
    assert user_alice.groups.count() == 0

    # Alice cannot add organizations
    api_client.force_authenticate(user_alice)
    response = api_client.post(
        reverse("users:add-organization-v1", kwargs={"pk": user_alice.id}),
        data=data_dict,
    )
    assert response.status_code == 403, response.content
    assert user_alice.groups.count() == 0

    # Staff can add organizations
    api_client.force_authenticate(user_staff)
    response = api_client.post(
        reverse("users:add-organization-v1", kwargs={"pk": user_alice.id}),
        data=data_dict,
    )
    assert response.status_code == 200, response.content
    assert user_alice.groups.count() == 1

    # Alice cannot remove organizations
    api_client.force_authenticate(user_alice)
    response = api_client.post(
        reverse("users:remove-organization-v1", kwargs={"pk": user_alice.id}),
        data=data_dict,
    )
    assert response.status_code == 403, response.content
    assert user_alice.groups.count() == 1

    # Staff can remove organizations
    api_client.force_authenticate(user_staff)
    response = api_client.post(
        reverse("users:remove-organization-v1", kwargs={"pk": user_alice.id}),
        data=data_dict,
    )
    assert response.status_code == 200, response.content
    assert user_alice.groups.count() == 0
