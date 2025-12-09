"""
Tests for PermissionSetViewSet endpoint: shared_permissions.
"""
import pytest
from rest_framework.reverse import reverse

from topobank.authorization.models import PermissionSet


@pytest.mark.django_db
class TestPermissionsSharedEndpoint:
    """Tests for the shared_permissions endpoint that finds users in multiple permission sets."""

    def test_shared_permissions_requires_authentication(self, api_client):
        """Test that unauthenticated users cannot access the shared_permissions endpoint."""
        url = reverse("authorization:permission-set-v2-shared")
        response = api_client.get(url, {"sets": [1, 2]})
        assert response.status_code == 403

    def test_shared_permissions_requires_sets_parameter(self, api_client, user_alice):
        """Test that the endpoint requires the 'sets' query parameter."""
        url = reverse("authorization:permission-set-v2-shared")

        api_client.force_authenticate(user_alice)
        response = api_client.get(url)
        assert response.status_code == 404
        assert "No permission set IDs provided" in str(response.data)

    def test_shared_permissions_validates_set_ids_format(self, api_client, user_alice):
        """Test that invalid set IDs return an error."""
        url = reverse("authorization:permission-set-v2-shared")

        api_client.force_authenticate(user_alice)
        response = api_client.get(url, {"sets": ["invalid", "ids"]})
        assert response.status_code == 404
        assert "Invalid permission set ID format" in str(response.data)

    def test_shared_permissions_requires_accessible_permission_sets(
        self, api_client, user_alice, user_bob
    ):
        """Test that users can only query permission sets they have access to."""
        # Create two permission sets that Alice doesn't have access to
        perm_set1 = PermissionSet.objects.create(user=user_bob, allow="full")
        perm_set2 = PermissionSet.objects.create(user=user_bob, allow="full")

        url = reverse("authorization:permission-set-v2-shared")

        api_client.force_authenticate(user_alice)
        response = api_client.get(url, {"sets": [perm_set1.id, perm_set2.id]})
        assert response.status_code == 404
        assert "No accessible permission sets found" in str(response.data)

    def test_shared_permissions_requires_all_sets_to_exist(
        self, api_client, one_line_scan
    ):
        """Test that all provided set IDs must exist."""
        surface = one_line_scan.surface

        url = reverse("authorization:permission-set-v2-shared")

        api_client.force_authenticate(surface.created_by)
        # Mix valid and invalid IDs
        response = api_client.get(url, {"sets": [surface.permissions.id, 99999]})
        assert response.status_code == 404
        assert "do not exist or are inaccessible" in str(response.data)

    def test_shared_permissions_finds_users_in_all_sets(
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

        url = reverse("authorization:permission-set-v2-shared")

        api_client.force_authenticate(user_alice)
        response = api_client.get(
            url, {"sets": [perm_set1.id, perm_set2.id, perm_set3.id]}
        )
        assert response.status_code == 200

        user_ids = [item["user"]["id"] for item in response.data["user_permissions"]]

        # Only Alice should be in the result (appears in all three sets)
        assert user_alice.id in user_ids
        assert user_bob.id not in user_ids

    def test_shared_permissions_returns_lowest_permission_level(
        self, api_client, user_alice, user_bob
    ):
        """Test that the shared returns the lowest permission level across all sets."""
        # Create two permission sets
        perm_set1 = PermissionSet.objects.create(user=user_alice, allow="full")
        perm_set2 = PermissionSet.objects.create(user=user_alice, allow="full")

        # Bob has 'full' in set 1 but 'view' in set 2
        perm_set1.grant_for_user(user_bob, "full")
        perm_set2.grant_for_user(user_bob, "view")

        url = reverse("authorization:permission-set-v2-shared")

        api_client.force_authenticate(user_alice)
        response = api_client.get(url, {"sets": [perm_set1.id, perm_set2.id]})
        assert response.status_code == 200

        # Find Bob in the results
        bob_data = next(
            item for item in response.data["user_permissions"] if item["user"]["id"] == user_bob.id
        )

        # The permission should be 'view' (the lowest across both sets)
        assert bob_data["allow"] == "view"

    def test_shared_permissions_with_organization_permissions(
        self, api_client, user_alice, user_bob, org_blofield
    ):
        """Test that shared considers organization permissions."""
        # Create two permission sets
        perm_set1 = PermissionSet.objects.create(user=user_alice, allow="full")
        perm_set2 = PermissionSet.objects.create(user=user_alice, allow="full")

        # Add Bob to the organization
        org_blofield.add(user_bob)

        # Grant organization permissions
        perm_set1.grant_for_organization(org_blofield, "edit")
        perm_set2.grant_for_organization(org_blofield, "view")

        url = reverse("authorization:permission-set-v2-shared")

        api_client.force_authenticate(user_alice)
        response = api_client.get(url, {"sets": [perm_set1.id, perm_set2.id]})
        assert response.status_code == 200

        user_ids = [item["user"]["id"] for item in response.data["user_permissions"]]

        # Bob should appear (has organization permission in both sets)
        assert user_bob.id in user_ids

        # Find Bob's permission level
        bob_data = next(
            item for item in response.data["user_permissions"] if item["user"]["id"] == user_bob.id
        )

        # Should be 'view' (lowest of edit and view)
        assert bob_data["allow"] == "view"

    def test_shared_permissions_prefers_direct_over_organization_permissions(
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

        url = reverse("authorization:permission-set-v2-shared")

        api_client.force_authenticate(user_alice)
        response = api_client.get(url, {"sets": [perm_set1.id, perm_set2.id]})
        assert response.status_code == 200

        bob_data = next(
            item for item in response.data["user_permissions"] if item["user"]["id"] == user_bob.id
        )

        # Should be 'edit' (min of 'full' from set1 and 'edit' from set2)
        assert bob_data["allow"] == "edit"

    def test_shared_permissions_with_single_set(self, api_client, user_alice, user_bob):
        """Test shared with a single permission set."""
        perm_set = PermissionSet.objects.create(user=user_alice, allow="full")
        perm_set.grant_for_user(user_bob, "view")

        url = reverse("authorization:permission-set-v2-shared")

        api_client.force_authenticate(user_alice)
        response = api_client.get(url, {"sets": [perm_set.id]})
        assert response.status_code == 200

        user_ids = [item["user"]["id"] for item in response.data["user_permissions"]]
        assert user_alice.id in user_ids
        assert user_bob.id in user_ids

    def test_shared_permissions_returns_only_common_users(
        self, api_client, user_alice, user_bob
    ):
        """Test that shared returns empty list when no users appear in all sets."""
        # Create two permission sets owned by Alice
        perm_set1 = PermissionSet.objects.create(user=user_alice, allow="full")
        perm_set2 = PermissionSet.objects.create(user=user_alice, allow="full")

        # Grant Bob access to only one set
        perm_set1.grant_for_user(user_bob, "view")

        url = reverse("authorization:permission-set-v2-shared")

        api_client.force_authenticate(user_alice)
        response = api_client.get(url, {"sets": [perm_set1.id, perm_set2.id]})
        assert response.status_code == 200

        user_ids = [item["user"]["id"] for item in response.data["user_permissions"]]

        # Only Alice should appear (she has access to both)
        # Bob only has access to perm_set1, not perm_set2
        assert user_alice.id in user_ids
        assert user_bob.id not in user_ids

    def test_shared_permissions_results_sorted_by_name(
        self, api_client, user_alice, user_bob
    ):
        """Test that results are sorted by name."""
        perm_set = PermissionSet.objects.create(user=user_alice, allow="full")

        # Grant permissions to multiple users
        perm_set.grant_for_user(user_bob, "view")
        perm_set.grant_for_user(user_alice, "full")

        url = reverse("authorization:permission-set-v2-shared")

        api_client.force_authenticate(user_alice)
        response = api_client.get(url, {"sets": [perm_set.id]})
        assert response.status_code == 200

        # Get usernames from the user name field
        user_names = [item["user"]["name"] for item in response.data["user_permissions"]]

        # Should be sorted alphabetically
        assert user_names == sorted(user_names)

    def test_shared_permissions_with_three_permission_levels(
        self, api_client, user_alice, user_bob
    ):
        """Test shared correctly identifies minimum across three permission levels."""
        # Create three permission sets
        perm_set1 = PermissionSet.objects.create(user=user_alice, allow="full")
        perm_set2 = PermissionSet.objects.create(user=user_alice, allow="full")
        perm_set3 = PermissionSet.objects.create(user=user_alice, allow="full")

        # Bob has view, edit, full across three sets
        perm_set1.grant_for_user(user_bob, "view")
        perm_set2.grant_for_user(user_bob, "edit")
        perm_set3.grant_for_user(user_bob, "full")

        url = reverse("authorization:permission-set-v2-shared")

        api_client.force_authenticate(user_alice)
        response = api_client.get(
            url, {"sets": [perm_set1.id, perm_set2.id, perm_set3.id]}
        )
        assert response.status_code == 200

        bob_data = next(
            item for item in response.data["user_permissions"] if item["user"]["id"] == user_bob.id
        )

        # Should be 'view' (the minimum)
        assert bob_data["allow"] == "view"

    def test_shared_permissions_is_unique_when_same_permission(
        self, api_client, user_alice, user_bob
    ):
        """Test that is_unique is True when user has same permission across all sets."""
        # Create two permission sets
        perm_set1 = PermissionSet.objects.create(user=user_alice, allow="full")
        perm_set2 = PermissionSet.objects.create(user=user_alice, allow="full")

        # Bob has 'view' in both sets
        perm_set1.grant_for_user(user_bob, "view")
        perm_set2.grant_for_user(user_bob, "view")

        url = reverse("authorization:permission-set-v2-shared")

        api_client.force_authenticate(user_alice)
        response = api_client.get(url, {"sets": [perm_set1.id, perm_set2.id]})
        assert response.status_code == 200

        bob_data = next(
            item for item in response.data["user_permissions"] if item["user"]["id"] == user_bob.id
        )

        # is_unique should be True since Bob has 'view' in both sets
        assert bob_data["is_unique"] is True
        assert bob_data["allow"] == "view"

    def test_shared_permissions_is_unique_false_when_different_permissions(
        self, api_client, user_alice, user_bob
    ):
        """Test that is_unique is False when user has different permissions across sets."""
        # Create two permission sets
        perm_set1 = PermissionSet.objects.create(user=user_alice, allow="full")
        perm_set2 = PermissionSet.objects.create(user=user_alice, allow="full")

        # Bob has 'full' in set 1 but 'view' in set 2
        perm_set1.grant_for_user(user_bob, "full")
        perm_set2.grant_for_user(user_bob, "view")

        url = reverse("authorization:permission-set-v2-shared")

        api_client.force_authenticate(user_alice)
        response = api_client.get(url, {"sets": [perm_set1.id, perm_set2.id]})
        assert response.status_code == 200

        bob_data = next(
            item for item in response.data["user_permissions"] if item["user"]["id"] == user_bob.id
        )

        # is_unique should be False since Bob has different permissions
        assert bob_data["is_unique"] is False
        # Should return the lowest ('view')
        assert bob_data["allow"] == "view"

    def test_shared_permissions_is_current_user(
        self, api_client, user_alice, user_bob
    ):
        """Test that is_current_user is correctly set."""
        perm_set = PermissionSet.objects.create(user=user_alice, allow="full")
        perm_set.grant_for_user(user_bob, "view")

        url = reverse("authorization:permission-set-v2-shared")

        api_client.force_authenticate(user_alice)
        response = api_client.get(url, {"sets": [perm_set.id]})
        assert response.status_code == 200

        # Find Alice and Bob in the results
        alice_data = next(
            item for item in response.data["user_permissions"] if item["user"]["id"] == user_alice.id
        )
        bob_data = next(
            item for item in response.data["user_permissions"] if item["user"]["id"] == user_bob.id
        )

        # Alice is the authenticated user, so is_current_user should be True
        assert alice_data["is_current_user"] is True
        # Bob is not the authenticated user, so is_current_user should be False
        assert bob_data["is_current_user"] is False

    def test_shared_permissions_response_structure(
        self, api_client, user_alice
    ):
        """Test that the response has the correct structure with user_permissions and organization_permissions."""
        perm_set = PermissionSet.objects.create(user=user_alice, allow="full")

        url = reverse("authorization:permission-set-v2-shared")

        api_client.force_authenticate(user_alice)
        response = api_client.get(url, {"sets": [perm_set.id]})
        assert response.status_code == 200

        # Verify response structure
        assert "user_permissions" in response.data
        assert "organization_permissions" in response.data
        assert isinstance(response.data["user_permissions"], list)
        assert isinstance(response.data["organization_permissions"], list)

        # Verify user_permissions structure
        if len(response.data["user_permissions"]) > 0:
            user_perm = response.data["user_permissions"][0]
            assert "user" in user_perm
            assert "allow" in user_perm
            assert "is_current_user" in user_perm
            assert "is_unique" in user_perm
