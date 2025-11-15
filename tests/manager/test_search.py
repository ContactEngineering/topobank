"""Test related to searching"""

import pytest
from django.conf import settings
from django.test import override_settings

from topobank.testing.factories import SurfaceFactory, Topography1DFactory, UserFactory
from topobank.testing.utils import search_surfaces


@pytest.fixture
def user_three_surfaces_four_topographies():
    settings.DELETE_EXISTING_FILES = True
    #
    # Create some database objects
    #
    user = UserFactory()
    surface1 = SurfaceFactory(created_by=user, category="exp")
    surface2 = SurfaceFactory(created_by=user, category="sim")
    surface3 = SurfaceFactory(created_by=user, category="dum")

    topo1a = Topography1DFactory(surface=surface1)
    topo1b = Topography1DFactory(surface=surface1)
    topo2a = Topography1DFactory(surface=surface2)
    topo2b = Topography1DFactory(surface=surface2)
    # no topography for surface3 on purpose

    return user, surface1, surface2, surface3, topo1a, topo1b, topo2a, topo2b


# FIXME: This test appears to pick up datasets from other tests that ran before; not
# sure how to clean the database before this test.
@pytest.mark.skip
@override_settings(DELETE_EXISTING_FILES=True)
@pytest.mark.django_db
def test_search_expressions(api_client):
    user = UserFactory()

    surface1 = SurfaceFactory(created_by=user)

    topo1a = Topography1DFactory(surface=surface1, description="a big tiger")
    topo1b = Topography1DFactory(surface=surface1, description="a big elephant")
    topo1c = Topography1DFactory(
        surface=surface1, description="Find this here and a small ant"
    )
    topo1d = Topography1DFactory(surface=surface1, description="not me, big snake")

    surface2 = SurfaceFactory(created_by=user)

    topo2a = Topography1DFactory(surface=surface2, name="Measurement 2A")
    Topography1DFactory(
        surface=surface2, name="Measurement 2B", description="a small lion"
    )

    #
    # Set some tags
    #
    topo1b.tags = ["bike"]
    topo1b.save()
    topo1c.tags = ["transport/bike"]
    topo1c.save()
    topo1d.tags = ["bike"]
    topo1d.save()

    # simple search for a topography by name given a phrase
    api_client.force_login(user)
    result = search_surfaces(api_client, f"'{topo2a.name}'")
    assert len(result) == 1  # one surface
    assert len(result[0]["topographies"]) == 1  # one topography
    assert result[0]["topographies"][0]["name"] == topo2a.name

    # AND search for topographies by name
    result = search_surfaces(api_client, f'"{topo2a.name}" "{topo1a.name}"')
    assert len(result) == 0  # no surfaces

    # OR search for topographies by name
    result = search_surfaces(api_client, f'"{topo2a.name}" OR "{topo1a.name}"')
    assert len(result) == 2  # two surfaces
    # noinspection DuplicatedCode
    assert len(result[0]["topographies"]) == 1  # one topography
    assert len(result[1]["topographies"]) == 1  # one topography
    assert result[0]["topographies"][0]["name"] == topo1a.name
    assert result[1]["topographies"][0]["name"] == topo2a.name

    # Exclusion using '-'
    result = search_surfaces(api_client, "-elephant")
    assert len(result) == 2
    assert result[0]["name"] == surface1.name
    assert result[1]["name"] == surface2.name
    assert len(result[0]["topographies"]) == 3  # here one measurement is excluded
    assert len(result[1]["topographies"]) == 2

    # Searching nearby
    result = search_surfaces(api_client, "Find * here")
    assert len(result) == 1
    assert result[0]["name"] == surface1.name
    assert len(result[0]["topographies"]) == 1  # here one measurement has it
    assert (
        result[0]["topographies"][0]["description"] == "Find this here and a small ant"
    )

    # more complex search expression using a phrase
    #
    # Parentheses do not work with 'websearch' for simplicity.
    #
    # (NOT) binds most tightly, "quoted text" (FOLLOWED BY) next most tightly,
    # then AND (default if no parameter), with OR binding the least tightly.
    #

    # result = search_surfaces(f'bike AND "a big" or "a small" -"not me"')
    result = search_surfaces(api_client, "bike -snake big")

    assert len(result) == 1  # surface 2 is excluded because there is no "bike"
    assert result[0]["name"] == surface1.name
    assert len(result[0]["topographies"]) == 1
    assert (
        result[0]["topographies"][0]["name"] == topo1b.name
    )  # topo1d is excluded because of 'not me'


# FIXME: This test appears to pick up datasets from other tests that ran before; not
# sure how to clean the database before this test.
@pytest.mark.skip
@override_settings(DELETE_EXISTING_FILES=True)
@pytest.mark.django_db
def test_search_for_user(api_client):
    user1 = UserFactory(name="Bob Marley")
    user2 = UserFactory(name="Bob Dylan")

    surf1 = SurfaceFactory(created_by=user1)
    surf2 = SurfaceFactory(created_by=user2)

    #
    # So far nothing has been shared
    #
    # User 1 searches
    api_client.force_login(user1)
    result = search_surfaces(api_client, "Bob")
    assert len(result) == 1
    assert result[0]["name"] == surf1.name
    assert len(result[0]["topographies"]) == 0

    result = search_surfaces(api_client, "Marley")
    assert len(result) == 1
    assert result[0]["name"] == surf1.name
    assert len(result[0]["topographies"]) == 0

    result = search_surfaces(api_client, "Dylan")
    assert len(result) == 0

    # User 2 searches
    api_client.force_login(user2)
    result = search_surfaces(api_client, "Bob")
    assert len(result) == 1
    assert result[0]["name"] == surf2.name
    assert len(result[0]["topographies"]) == 0

    result = search_surfaces(api_client, "Marley")
    assert len(result) == 0

    result = search_surfaces(api_client, "Dylan")
    assert len(result) == 1
    assert result[0]["name"] == surf2.name
    assert len(result[0]["topographies"]) == 0

    #
    # User1 shares his surface with user2
    #
    surf1.grant_permission(user2, "edit")

    # User 2 searches, now surface of user 1 is also visible
    result = search_surfaces(api_client, "Bob")
    assert len(result) == 2
    assert set(r["name"] for r in result) == set((surf1.name, surf2.name))
    assert len(result[0]["topographies"]) == 0
    assert len(result[1]["topographies"]) == 0

    result = search_surfaces(api_client, "Marley")
    assert len(result) == 1
    assert result[0]["name"] == surf1.name
    assert len(result[0]["topographies"]) == 0

    result = search_surfaces(api_client, "Dylan")
    assert len(result) == 1
    assert result[0]["name"] == surf2.name
    assert len(result[0]["topographies"]) == 0

    #
    # User1 adds a topography to shared surface, it should be findable by both users using first user's name
    #
    topo1a = Topography1DFactory(surface=surf1, created_by=user1)

    # User 1 searches, finds also topography
    api_client.force_login(user1)
    result = search_surfaces(api_client, "Bob")
    assert len(result) == 1
    assert result[0]["name"] == surf1.name
    assert len(result[0]["topographies"]) == 1

    result = search_surfaces(api_client, "Marley")
    assert len(result) == 1
    assert result[0]["name"] == surf1.name
    assert len(result[0]["topographies"]) == 1

    result = search_surfaces(api_client, "Dylan")
    assert len(result) == 0

    # User 2 searches, finds also topography of user 1 in shared surface
    api_client.force_login(user2)
    result = search_surfaces(api_client, "Bob")
    assert len(result) == 2
    assert set(r["name"] for r in result) == set((surf1.name, surf2.name))
    assert len(result[0]["topographies"]) == 1
    assert len(result[1]["topographies"]) == 0  # user2's own surface has no topography

    result = search_surfaces(api_client, "Marley")
    assert len(result) == 1
    assert result[0]["name"] == surf1.name
    assert len(result[0]["topographies"]) == 1

    result = search_surfaces(api_client, "Dylan")
    assert len(result) == 1
    assert result[0]["name"] == surf2.name
    assert len(result[0]["topographies"]) == 0

    #
    # User2 adds a topography to shared surface, it should be findable by both users using user2's last name
    #
    topo1b = Topography1DFactory(surface=surf1, created_by=user2)

    # User 1 searches, finds topographies, depending on search term
    api_client.force_login(user1)
    result = search_surfaces(api_client, "Bob")
    assert len(result) == 1
    assert result[0]["name"] == surf1.name
    assert len(result[0]["topographies"]) == 2

    result = search_surfaces(api_client, "Marley")
    assert len(result) == 1
    assert result[0]["name"] == surf1.name
    assert (
        len(result[0]["topographies"]) == 1
    )  # topography uploaded by user2 should not be shown
    assert result[0]["topographies"][0]["name"] == topo1a.name

    result = search_surfaces(api_client, "Dylan")
    assert len(result) == 1
    assert (
        result[0]["name"] == surf1.name
    )  # now own surface is also listed with one topography matching "Dylan"
    assert (
        len(result[0]["topographies"]) == 1
    )  # topography uploaded by user2 should be shown alone
    assert result[0]["topographies"][0]["name"] == topo1b.name

    # User 2 searches, finds also topography of user 1 in shared surface
    api_client.force_login(user2)
    result = search_surfaces(api_client, "Bob")
    assert len(result) == 2
    assert set(r["name"] for r in result) == set((surf1.name, surf2.name))
    assert len(result[0]["topographies"]) == 2
    assert len(result[1]["topographies"]) == 0  # user2's own surface has no topography

    result = search_surfaces(api_client, "Marley")
    assert len(result) == 1
    assert result[0]["name"] == surf1.name
    assert (
        len(result[0]["topographies"]) == 1
    )  # topography uploaded by user1 should be shown alone
    assert result[0]["topographies"][0]["name"] == topo1a.name

    result = search_surfaces(api_client, "Dylan")
    assert len(result) == 2
    assert set(r["name"] for r in result) == set(
        (surf1.name, surf2.name)
    )  # now also surf1 is listed
    assert result[0]["name"] == surf1.name
    assert (
        len(result[0]["topographies"]) == 1
    )  # topography uploaded by user1 should be shown alone
    assert result[0]["topographies"][0]["name"] == topo1b.name
    assert result[1]["name"] == surf2.name
    assert len(result[1]["topographies"]) == 0
