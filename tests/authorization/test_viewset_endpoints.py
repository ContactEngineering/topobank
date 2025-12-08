"""
Tests for PermissionSetViewSet endpoints: users_list and permissions_intersection.
"""
import pytest
from rest_framework.reverse import reverse

from topobank.authorization.models import PermissionSet


@pytest.mark.django_db
class TestUsersListEndpoint:
    """Tests for the users_list endpoint that returns all users with permissions on a permission set."""

    def test_users_list_requires_authentication(self, api_client, one_line_scan):
        """Test that unauthenticated users cannot access the users list."""
        surface = one_line_scan.surface
        url = reverse(
            "authorization:permission-set-v2-users",
            kwargs={"pk": surface.permissions.id}
        )
        response = api_client.get(url)
        assert response.status_code == 403

    def test_users_list_requires_view_permission(self, api_client, one_line_scan, user_alice):
        """Test that users without view permission get 403."""
        surface = one_line_scan.surface
        url = reverse(
            "authorization:permission-set-v2-users",
            kwargs={"pk": surface.permissions.id}
        )

        # Alice has no permission
        api_client.force_authenticate(user_alice)
        response = api_client.get(url)
        assert response.status_code == 403

    def test_users_list_with_view_permission(self, api_client, one_line_scan, user_alice):
        """Test that users with view permission can list users."""
        surface = one_line_scan.surface

        # Grant Alice view permission
        surface.permissions.grant_for_user(user_alice, "view")

        url = reverse(
            "authorization:permission-set-v2-users",
            kwargs={"pk": surface.permissions.id}
        )

        api_client.force_authenticate(user_alice)
        response = api_client.get(url)
        assert response.status_code == 200
        assert isinstance(response.data, list)

        # Should have at least 2 users: the creator and Alice
        assert len(response.data) >= 2

        # Check that the response contains user information
        user_ids = [item["user"]["id"] for item in response.data]
        assert user_alice.id in user_ids
        assert surface.created_by.id in user_ids

    def test_users_list_shows_only_direct_user_permissions(
        self, api_client, one_line_scan, user_alice, user_bob, org_blofield
    ):
        """Test that users_list returns only direct user permissions, not organization permissions."""
        surface = one_line_scan.surface

        # Add Alice directly with view permission
        surface.permissions.grant_for_user(user_alice, "view")

        # Add Bob through organization with edit permission
        org_blofield.add(user_bob)
        surface.permissions.grant_for_organization(org_blofield, "edit")

        url = reverse(
            "authorization:permission-set-v2-users",
            kwargs={"pk": surface.permissions.id}
        )

        api_client.force_authenticate(surface.created_by)
        response = api_client.get(url)
        assert response.status_code == 200

        user_ids = [item["user"]["id"] for item in response.data]

        # Alice should be in the list (direct user permission)
        assert user_alice.id in user_ids

        # Bob should NOT be in the list (only has organization permission)
        assert user_bob.id not in user_ids

    def test_users_list_includes_permission_levels(self, api_client, one_line_scan, user_alice, user_bob):
        """Test that the response includes the correct permission levels."""
        surface = one_line_scan.surface

        # Grant different permission levels
        surface.permissions.grant_for_user(user_alice, "view")
        surface.permissions.grant_for_user(user_bob, "full")

        url = reverse(
            "authorization:permission-set-v2-users",
            kwargs={"pk": surface.permissions.id}
        )

        api_client.force_authenticate(surface.created_by)
        response = api_client.get(url)
        assert response.status_code == 200

        # Create a mapping of user ID to permission
        user_perms = {item["user"]["id"]: item["allow"] for item in response.data}

        assert user_perms[user_alice.id] == "view"
        assert user_perms[user_bob.id] == "full"

    def test_users_list_for_nonexistent_permission_set(self, api_client, user_alice):
        """Test that requesting a nonexistent permission set returns 404."""
        url = reverse(
            "authorization:permission-set-v2-users",
            kwargs={"pk": 99999}
        )

        api_client.force_authenticate(user_alice)
        response = api_client.get(url)
        assert response.status_code == 404


@pytest.mark.django_db
class TestPermissionsIntersectionEndpoint:
    """Tests for the permissions_intersection endpoint that finds users in multiple permission sets."""

    def test_intersection_requires_authentication(self, api_client):
        """Test that unauthenticated users cannot access the intersection endpoint."""
        url = reverse("authorization:permission-set-v2-intersection")
        response = api_client.get(url, {"sets": [1, 2]})
        assert response.status_code == 403

    def test_intersection_requires_sets_parameter(self, api_client, user_alice):
        """Test that the endpoint requires the 'sets' query parameter."""
        url = reverse("authorization:permission-set-v2-intersection")

        api_client.force_authenticate(user_alice)
        response = api_client.get(url)
        assert response.status_code == 404
        assert "No permission set IDs provided" in str(response.data)

    def test_intersection_validates_set_ids_format(self, api_client, user_alice):
        """Test that invalid set IDs return an error."""
        url = reverse("authorization:permission-set-v2-intersection")

        api_client.force_authenticate(user_alice)
        response = api_client.get(url, {"sets": ["invalid", "ids"]})
        assert response.status_code == 404
        assert "Invalid permission set ID format" in str(response.data)

    def test_intersection_requires_accessible_permission_sets(
        self, api_client, user_alice, user_bob
    ):
        """Test that users can only query permission sets they have access to."""
        # Create two permission sets that Alice doesn't have access to
        perm_set1 = PermissionSet.objects.create(user=user_bob, allow="full")
        perm_set2 = PermissionSet.objects.create(user=user_bob, allow="full")

        url = reverse("authorization:permission-set-v2-intersection")

        api_client.force_authenticate(user_alice)
        response = api_client.get(url, {"sets": [perm_set1.id, perm_set2.id]})
        assert response.status_code == 404
        assert "No accessible permission sets found" in str(response.data)

    def test_intersection_requires_all_sets_to_exist(
        self, api_client, one_line_scan
    ):
        """Test that all provided set IDs must exist."""
        surface = one_line_scan.surface

        url = reverse("authorization:permission-set-v2-intersection")

        api_client.force_authenticate(surface.created_by)
        # Mix valid and invalid IDs
        response = api_client.get(url, {"sets": [surface.permissions.id, 99999]})
        assert response.status_code == 404
        assert "do not exist or are inaccessible" in str(response.data)

    def test_intersection_finds_users_in_all_sets(
        self, api_client, user_alice, user_bob
    ):
        """Test that the endpoint finds users that appear in all specified sets."""
        # Create three permission sets
        perm_set1 = PermissionSet.objects.create(user=user_alice, allow="full")
        perm_set2 = PermissionSet.objects.create(user=user_alice, allow="full")
        perm_set3 = PermissionSet.objects.create(user=user_alice, allow="full")

        # Grant permissions:
        # Alice: has access to all three sets
        perm_set1.grant_for_user(user_alice, "view")
        perm_set2.grant_for_user(user_alice, "edit")
        perm_set3.grant_for_user(user_alice, "full")

        # Bob: has access to only two sets
        perm_set1.grant_for_user(user_bob, "view")
        perm_set2.grant_for_user(user_bob, "view")

        url = reverse("authorization:permission-set-v2-intersection")

        api_client.force_authenticate(user_alice)
        response = api_client.get(
            url, {"sets": [perm_set1.id, perm_set2.id, perm_set3.id]}
        )
        assert response.status_code == 200

        user_ids = [item["user"]["id"] for item in response.data]

        # Only Alice should be in the result (appears in all three sets)
        assert user_alice.id in user_ids
        assert user_bob.id not in user_ids

    def test_intersection_returns_lowest_permission_level(
        self, api_client, user_alice, user_bob
    ):
        """Test that the intersection returns the lowest permission level across all sets."""
        # Create two permission sets
        perm_set1 = PermissionSet.objects.create(user=user_alice, allow="full")
        perm_set2 = PermissionSet.objects.create(user=user_alice, allow="full")

        # Bob has 'full' in set 1 but 'view' in set 2
        perm_set1.grant_for_user(user_bob, "full")
        perm_set2.grant_for_user(user_bob, "view")

        url = reverse("authorization:permission-set-v2-intersection")

        api_client.force_authenticate(user_alice)
        response = api_client.get(url, {"sets": [perm_set1.id, perm_set2.id]})
        assert response.status_code == 200

        # Find Bob in the results
        bob_data = next(
            item for item in response.data if item["user"]["id"] == user_bob.id
        )

        # The permission should be 'view' (the lowest across both sets)
        assert bob_data["allow"] == "view"

    def test_intersection_with_organization_permissions(
        self, api_client, user_alice, user_bob, org_blofield
    ):
        """Test that intersection considers organization permissions."""
        # Create two permission sets
        perm_set1 = PermissionSet.objects.create(user=user_alice, allow="full")
        perm_set2 = PermissionSet.objects.create(user=user_alice, allow="full")

        # Add Bob to the organization
        org_blofield.add(user_bob)

        # Grant organization permissions
        perm_set1.grant_for_organization(org_blofield, "edit")
        perm_set2.grant_for_organization(org_blofield, "view")

        url = reverse("authorization:permission-set-v2-intersection")

        api_client.force_authenticate(user_alice)
        response = api_client.get(url, {"sets": [perm_set1.id, perm_set2.id]})
        assert response.status_code == 200

        user_ids = [item["user"]["id"] for item in response.data]

        # Bob should appear (has organization permission in both sets)
        assert user_bob.id in user_ids

        # Find Bob's permission level
        bob_data = next(
            item for item in response.data if item["user"]["id"] == user_bob.id
        )

        # Should be 'view' (lowest of edit and view)
        assert bob_data["allow"] == "view"

    def test_intersection_prefers_direct_over_organization_permissions(
        self, api_client, user_alice, user_bob, org_blofield
    ):
        """Test that when a user has both direct and org permissions, the higher is used per set."""
        # Create two permission sets
        perm_set1 = PermissionSet.objects.create(user=user_alice, allow="full")
        perm_set2 = PermissionSet.objects.create(user=user_alice, allow="full")

        # Add Bob to organization
        org_blofield.add(user_bob)

        # Set 1: Bob has direct 'full' and org 'view' - should use 'full'
        perm_set1.grant_for_user(user_bob, "full")
        perm_set1.grant_for_organization(org_blofield, "view")

        # Set 2: Bob has only direct 'edit'
        perm_set2.grant_for_user(user_bob, "edit")

        url = reverse("authorization:permission-set-v2-intersection")

        api_client.force_authenticate(user_alice)
        response = api_client.get(url, {"sets": [perm_set1.id, perm_set2.id]})
        assert response.status_code == 200

        bob_data = next(
            item for item in response.data if item["user"]["id"] == user_bob.id
        )

        # Should be 'edit' (min of 'full' from set1 and 'edit' from set2)
        assert bob_data["allow"] == "edit"

    def test_intersection_with_single_set(self, api_client, user_alice, user_bob):
        """Test intersection with a single permission set."""
        perm_set = PermissionSet.objects.create(user=user_alice, allow="full")
        perm_set.grant_for_user(user_bob, "view")

        url = reverse("authorization:permission-set-v2-intersection")

        api_client.force_authenticate(user_alice)
        response = api_client.get(url, {"sets": [perm_set.id]})
        assert response.status_code == 200

        user_ids = [item["user"]["id"] for item in response.data]
        assert user_alice.id in user_ids
        assert user_bob.id in user_ids

    def test_intersection_returns_only_common_users(
        self, api_client, user_alice, user_bob
    ):
        """Test that intersection returns empty list when no users appear in all sets."""
        # Create two permission sets owned by Alice
        perm_set1 = PermissionSet.objects.create(user=user_alice, allow="full")
        perm_set2 = PermissionSet.objects.create(user=user_alice, allow="full")

        # Grant Bob access to only one set
        perm_set1.grant_for_user(user_bob, "view")

        url = reverse("authorization:permission-set-v2-intersection")

        api_client.force_authenticate(user_alice)
        response = api_client.get(url, {"sets": [perm_set1.id, perm_set2.id]})
        assert response.status_code == 200

        user_ids = [item["user"]["id"] for item in response.data]

        # Only Alice should appear (she has access to both)
        # Bob only has access to perm_set1, not perm_set2
        assert user_alice.id in user_ids
        assert user_bob.id not in user_ids

    def test_intersection_results_sorted_by_username(
        self, api_client, user_alice, user_bob
    ):
        """Test that results are sorted by username."""
        perm_set = PermissionSet.objects.create(user=user_alice, allow="full")

        # Grant permissions to multiple users
        perm_set.grant_for_user(user_bob, "view")
        perm_set.grant_for_user(user_alice, "full")

        url = reverse("authorization:permission-set-v2-intersection")

        api_client.force_authenticate(user_alice)
        response = api_client.get(url, {"sets": [perm_set.id]})
        assert response.status_code == 200

        # Get usernames from the user name field
        usernames = [item["user"]["name"] for item in response.data]

        # Should be sorted alphabetically
        assert usernames == sorted(usernames)

    def test_intersection_with_three_permission_levels(
        self, api_client, user_alice, user_bob
    ):
        """Test intersection correctly identifies minimum across three permission levels."""
        # Create three permission sets
        perm_set1 = PermissionSet.objects.create(user=user_alice, allow="full")
        perm_set2 = PermissionSet.objects.create(user=user_alice, allow="full")
        perm_set3 = PermissionSet.objects.create(user=user_alice, allow="full")

        # Bob has view, edit, full across three sets
        perm_set1.grant_for_user(user_bob, "view")
        perm_set2.grant_for_user(user_bob, "edit")
        perm_set3.grant_for_user(user_bob, "full")

        url = reverse("authorization:permission-set-v2-intersection")

        api_client.force_authenticate(user_alice)
        response = api_client.get(
            url, {"sets": [perm_set1.id, perm_set2.id, perm_set3.id]}
        )
        assert response.status_code == 200

        bob_data = next(
            item for item in response.data if item["user"]["id"] == user_bob.id
        )

        # Should be 'view' (the minimum)
        assert bob_data["allow"] == "view"
