import pytest

from guardian.shortcuts import get_perms

from .utils import SurfaceFactory, UserFactory


@pytest.mark.django_db
def test_published_field():
    surface = SurfaceFactory()
    assert not surface.is_published
    surface.publish('cc0')
    assert surface.is_published


@pytest.mark.django_db
def test_permissions_for_published():
    surface = SurfaceFactory()
    user1 = surface.creator
    user2 = UserFactory()

    # before publishing, user1 is allowed everything,
    # user2 nothing
    assert set(get_perms(user1, surface)) == set(['view_surface', 'delete_surface', 'change_surface',
                                                  'share_surface', 'publish_surface'])
    assert get_perms(user2, surface) == []

    # after publishing, both users are only allowed viewing
    surface.publish('cc0')

    assert get_perms(user1, surface) == ['view_surface']
    assert get_perms(user2, surface) == ['view_surface']
