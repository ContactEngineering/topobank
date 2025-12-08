"""Tests for the tag_tree API view."""

import pytest
from django.urls import reverse
from rest_framework import status

from topobank.testing.factories import SurfaceFactory, TagFactory


@pytest.mark.django_db
class TestTagTreeView:
    """Test the tag_tree API endpoint."""

    @pytest.fixture
    def url(self):
        """Return the URL for the tag_tree endpoint."""
        return reverse("manager:tag-tree-v2")

    def test_tag_tree_requires_authentication(self, api_client, url):
        """Test that unauthenticated requests are rejected."""
        response = api_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_tag_tree_empty_when_no_tags(self, api_client, user_alice, url):
        """Test that an empty dict is returned when there are no tags."""
        api_client.force_login(user_alice)
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {}

    def test_tag_tree_single_tag(self, api_client, user_alice, url):
        """Test tree structure with a single tag."""
        surface = SurfaceFactory(created_by=user_alice)
        surface.grant_permission(user_alice, "view")
        tag = TagFactory(name="material")
        surface.tags.add(tag)

        api_client.force_login(user_alice)
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "material" in response.data
        assert response.data["material"]["surface_count"] == 1
        assert response.data["material"]["children"] == {}

    def test_tag_tree_hierarchical_tags(self, api_client, user_alice, url):
        """Test tree structure with hierarchical tags."""
        surface = SurfaceFactory(created_by=user_alice)
        surface.grant_permission(user_alice, "view")

        # Create hierarchical tags
        tag_material = TagFactory(name="material")
        tag_steel = TagFactory(name="material/steel")
        tag_stainless = TagFactory(name="material/steel/stainless")

        surface.tags.add(tag_material, tag_steel, tag_stainless)

        api_client.force_login(user_alice)
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK

        # Check root level
        assert "material" in response.data
        assert response.data["material"]["surface_count"] == 1

        # Check first level children
        children = response.data["material"]["children"]
        assert "material/steel" in children
        assert children["material/steel"]["surface_count"] == 1

        # Check second level children
        grandchildren = children["material/steel"]["children"]
        assert "material/steel/stainless" in grandchildren
        assert grandchildren["material/steel/stainless"]["surface_count"] == 1
        assert grandchildren["material/steel/stainless"]["children"] == {}

    def test_tag_tree_surface_counts_at_each_level(self, api_client, user_alice, url):
        """Test that surface counts are correct at each level."""
        # Create surfaces with different tag levels
        surface1 = SurfaceFactory(created_by=user_alice, name="surface1")
        surface1.grant_permission(user_alice, "view")
        surface1.tags.add(TagFactory(name="material"))

        surface2 = SurfaceFactory(created_by=user_alice, name="surface2")
        surface2.grant_permission(user_alice, "view")
        surface2.tags.add(TagFactory(name="material/steel"))

        surface3 = SurfaceFactory(created_by=user_alice, name="surface3")
        surface3.grant_permission(user_alice, "view")
        surface3.tags.add(TagFactory(name="material/steel/stainless"))

        api_client.force_login(user_alice)
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK

        # Each level should have exactly 1 surface with that exact tag
        assert response.data["material"]["surface_count"] == 1
        assert response.data["material"]["children"]["material/steel"]["surface_count"] == 1
        assert (
            response.data["material"]["children"]["material/steel"]["children"][
                "material/steel/stainless"
            ]["surface_count"]
            == 1
        )

    def test_tag_tree_multiple_surfaces_same_tag(self, api_client, user_alice, url):
        """Test counting multiple surfaces with the same tag."""
        tag = TagFactory(name="material")

        for i in range(3):
            surface = SurfaceFactory(created_by=user_alice, name=f"surface{i}")
            surface.grant_permission(user_alice, "view")
            surface.tags.add(tag)

        api_client.force_login(user_alice)
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["material"]["surface_count"] == 3

    def test_tag_tree_multiple_root_tags(self, api_client, user_alice, url):
        """Test tree with multiple root-level tags."""
        surface1 = SurfaceFactory(created_by=user_alice, name="surface1")
        surface1.grant_permission(user_alice, "view")
        surface1.tags.add(TagFactory(name="material"))

        surface2 = SurfaceFactory(created_by=user_alice, name="surface2")
        surface2.grant_permission(user_alice, "view")
        surface2.tags.add(TagFactory(name="location"))

        surface3 = SurfaceFactory(created_by=user_alice, name="surface3")
        surface3.grant_permission(user_alice, "view")
        surface3.tags.add(TagFactory(name="experiment"))

        api_client.force_login(user_alice)
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "material" in response.data
        assert "location" in response.data
        assert "experiment" in response.data
        assert response.data["material"]["surface_count"] == 1
        assert response.data["location"]["surface_count"] == 1
        assert response.data["experiment"]["surface_count"] == 1

    def test_tag_tree_with_root_filter(self, api_client, user_alice, url):
        """Test filtering the tree by a root tag."""
        surface = SurfaceFactory(created_by=user_alice)
        surface.grant_permission(user_alice, "view")

        # Create multiple tag hierarchies
        surface.tags.add(
            TagFactory(name="material"),
            TagFactory(name="material/steel"),
            TagFactory(name="material/steel/stainless"),
            TagFactory(name="location"),
            TagFactory(name="location/lab"),
        )

        api_client.force_login(user_alice)
        response = api_client.get(url, {"tag": "material"})

        assert response.status_code == status.HTTP_200_OK

        # Should only contain the material tree
        assert "material" in response.data
        assert "location" not in response.data

        # Check the subtree structure
        assert response.data["material"]["surface_count"] == 1
        assert "material/steel" in response.data["material"]["children"]
        assert (
            "material/steel/stainless"
            in response.data["material"]["children"]["material/steel"]["children"]
        )

    def test_tag_tree_with_root_filter_empty_result(self, api_client, user_alice, url):
        """Test filtering with a tag that doesn't exist returns empty dict."""
        surface = SurfaceFactory(created_by=user_alice)
        surface.grant_permission(user_alice, "view")
        surface.tags.add(TagFactory(name="material"))

        api_client.force_login(user_alice)
        response = api_client.get(url, {"tag": "nonexistent"})

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {}

    def test_tag_tree_with_root_filter_leaf_tag(self, api_client, user_alice, url):
        """Test filtering by a leaf tag (no children)."""
        surface = SurfaceFactory(created_by=user_alice)
        surface.grant_permission(user_alice, "view")
        surface.tags.add(
            TagFactory(name="material"),
            TagFactory(name="material/steel"),
        )

        api_client.force_login(user_alice)
        response = api_client.get(url, {"tag": "material/steel"})

        assert response.status_code == status.HTTP_200_OK
        assert "material/steel" in response.data
        assert response.data["material/steel"]["surface_count"] == 1
        assert response.data["material/steel"]["children"] == {}

    def test_tag_tree_excludes_deleted_surfaces(self, api_client, user_alice, url):
        """Test that deleted surfaces are not counted."""
        surface1 = SurfaceFactory(created_by=user_alice, name="surface1")
        surface1.grant_permission(user_alice, "view")
        tag = TagFactory(name="material")
        surface1.tags.add(tag)

        # Create a deleted surface with the same tag
        surface2 = SurfaceFactory(created_by=user_alice, name="surface2")
        surface2.grant_permission(user_alice, "view")
        surface2.tags.add(tag)
        surface2.delete()

        api_client.force_login(user_alice)
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # Should only count the non-deleted surface
        assert response.data["material"]["surface_count"] == 1

    def test_tag_tree_permission_filtering(self, api_client, user_alice, user_bob, url):
        """Test that users only see tags from surfaces they have permission to view."""
        # Alice's surface
        surface_alice = SurfaceFactory(created_by=user_alice, name="surface_alice")
        surface_alice.grant_permission(user_alice, "view")
        surface_alice.tags.add(TagFactory(name="material"))

        # Bob's surface (no permission for Alice)
        surface_bob = SurfaceFactory(created_by=user_bob, name="surface_bob")
        surface_bob.grant_permission(user_bob, "view")
        surface_bob.tags.add(TagFactory(name="location"))

        # Alice should only see her own surface's tags
        api_client.force_login(user_alice)
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "material" in response.data
        assert "location" not in response.data

    def test_tag_tree_with_shared_surface(self, api_client, user_alice, user_bob, url):
        """Test that shared surfaces are counted for both users."""
        # Create a surface owned by Alice but shared with Bob
        surface = SurfaceFactory(created_by=user_alice)
        surface.grant_permission(user_alice, "view")
        surface.grant_permission(user_bob, "view")
        surface.tags.add(TagFactory(name="material"))

        # Both users should see the tag
        api_client.force_login(user_alice)
        response_alice = api_client.get(url)

        api_client.force_login(user_bob)
        response_bob = api_client.get(url)

        assert response_alice.status_code == status.HTTP_200_OK
        assert response_bob.status_code == status.HTTP_200_OK
        assert response_alice.data["material"]["surface_count"] == 1
        assert response_bob.data["material"]["surface_count"] == 1

    def test_tag_tree_complex_hierarchy(self, api_client, user_alice, url):
        """Test a complex tree with multiple branches and levels."""
        surface = SurfaceFactory(created_by=user_alice)
        surface.grant_permission(user_alice, "view")

        # Create a complex tag hierarchy
        surface.tags.add(
            TagFactory(name="material"),
            TagFactory(name="material/metal"),
            TagFactory(name="material/metal/steel"),
            TagFactory(name="material/metal/aluminum"),
            TagFactory(name="material/polymer"),
            TagFactory(name="material/polymer/plastic"),
            TagFactory(name="location"),
            TagFactory(name="location/lab"),
            TagFactory(name="location/lab/room1"),
        )

        api_client.force_login(user_alice)
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK

        # Verify material branch
        assert "material" in response.data
        material_children = response.data["material"]["children"]
        assert "material/metal" in material_children
        assert "material/polymer" in material_children

        # Verify metal sub-branch
        metal_children = material_children["material/metal"]["children"]
        assert "material/metal/steel" in metal_children
        assert "material/metal/aluminum" in metal_children

        # Verify polymer sub-branch
        polymer_children = material_children["material/polymer"]["children"]
        assert "material/polymer/plastic" in polymer_children

        # Verify location branch
        assert "location" in response.data
        location_children = response.data["location"]["children"]
        assert "location/lab" in location_children
        lab_children = location_children["location/lab"]["children"]
        assert "location/lab/room1" in lab_children

    def test_tag_tree_surface_with_multiple_tags(self, api_client, user_alice, url):
        """Test a surface with multiple tags from different hierarchies."""
        surface = SurfaceFactory(created_by=user_alice)
        surface.grant_permission(user_alice, "view")

        # Add tags from different hierarchies
        surface.tags.add(
            TagFactory(name="material"),
            TagFactory(name="material/steel"),
            TagFactory(name="location"),
        )

        api_client.force_login(user_alice)
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK

        # All tags should be present
        assert "material" in response.data
        assert "location" in response.data
        assert "material/steel" in response.data["material"]["children"]

        # Same surface counted in both hierarchies
        assert response.data["material"]["surface_count"] == 1
        assert response.data["location"]["surface_count"] == 1

    def test_tag_tree_zero_count_intermediate_nodes(self, api_client, user_alice, url):
        """Test that intermediate nodes show zero count when no surface has that exact tag."""
        # Only tag the leaf, not the intermediate nodes
        surface = SurfaceFactory(created_by=user_alice)
        surface.grant_permission(user_alice, "view")
        surface.tags.add(TagFactory(name="material/steel/stainless"))

        api_client.force_login(user_alice)
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK

        # The tree should still be built, but intermediate nodes have 0 count
        assert "material" in response.data
        assert response.data["material"]["surface_count"] == 0

        assert "material/steel" in response.data["material"]["children"]
        assert response.data["material"]["children"]["material/steel"]["surface_count"] == 0

        assert (
            "material/steel/stainless"
            in response.data["material"]["children"]["material/steel"]["children"]
        )
        assert (
            response.data["material"]["children"]["material/steel"]["children"][
                "material/steel/stainless"
            ]["surface_count"]
            == 1
        )

    def test_tag_tree_with_root_filter_includes_descendants_only(
        self, api_client, user_alice, url
    ):
        """Test that root filter includes descendants but not siblings."""
        surface = SurfaceFactory(created_by=user_alice)
        surface.grant_permission(user_alice, "view")

        # Create tags with siblings
        surface.tags.add(
            TagFactory(name="material"),
            TagFactory(name="material/steel"),
            TagFactory(name="material/steel/stainless"),
            TagFactory(name="material/aluminum"),  # sibling of steel
        )

        api_client.force_login(user_alice)
        response = api_client.get(url, {"tag": "material/steel"})

        assert response.status_code == status.HTTP_200_OK

        # Should include material/steel and its descendants
        assert "material/steel" in response.data
        assert (
            "material/steel/stainless" in response.data["material/steel"]["children"]
        )

        # Should not include siblings (aluminum)
        assert "material/aluminum" not in response.data["material/steel"]["children"]
        # Should not include parent as a separate key
        assert "material" not in response.data or response.data.get("material") is None

    def test_tag_tree_surface_with_no_tags(self, api_client, user_alice, url):
        """Test that surfaces without tags don't affect the tree."""
        surface1 = SurfaceFactory(created_by=user_alice, name="surface1")
        surface1.grant_permission(user_alice, "view")
        surface1.tags.add(TagFactory(name="material"))

        # Surface without tags
        surface2 = SurfaceFactory(created_by=user_alice, name="surface2")
        surface2.grant_permission(user_alice, "view")

        api_client.force_login(user_alice)
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "material" in response.data
        assert response.data["material"]["surface_count"] == 1
