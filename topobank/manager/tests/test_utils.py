"""
Tests for the interface to topography files
and other things in topobank.manager.utils
"""

import pytest

from ..utils import subjects_to_dict, subjects_from_dict, subjects_to_base64, subjects_from_base64, surfaces_for_user
from ..models import Surface, Topography

from .utils import SurfaceFactory, UserFactory


def test_subjects_to_dict(user_three_topographies_three_surfaces_three_tags):
    topo1, topo2, topo3 = Topography.objects.all()
    surf1, surf2, surf3 = Surface.objects.all()
    assert subjects_from_dict(subjects_to_dict([topo1, topo2, surf3])) == [topo1, topo2, surf3]


def test_subjects_to_url(user_three_topographies_three_surfaces_three_tags):
    topo1, topo2, topo3 = Topography.objects.all()
    surf1, surf2, surf3 = Surface.objects.all()
    assert subjects_from_base64(subjects_to_base64([topo1, topo2, surf3])) == [topo1, topo2, surf3]


@pytest.mark.django_db
def test_surfaces_for_user(user_three_topographies_three_surfaces_three_tags):
    user1, (topo1a, topo1b, topo2a), (surface1, surface2, surface3), (tag1, tag2, tag3) \
        = user_three_topographies_three_surfaces_three_tags

    user2 = UserFactory()

    surface4 = SurfaceFactory(creator=user2)
    surface5 = SurfaceFactory(creator=user2)

    surface4.share(user1)

    def assert_same_surface_lists(l1, l2):
        assert sorted(l1, key=lambda s: s.id) == sorted(l2, key=lambda s: s.id)

    assert_same_surface_lists(surfaces_for_user(user1), [surface1, surface2, surface3, surface4])
    assert_same_surface_lists(surfaces_for_user(user2), [surface4, surface5])
    assert_same_surface_lists(surfaces_for_user(user1, perms=['view_surface', 'change_surface']),
                              [surface1, surface2, surface3])

    surface4.set_permissions(user1, 'edit')
    assert_same_surface_lists(surfaces_for_user(user1, perms=['view_surface', 'change_surface']),
                              [surface1, surface2, surface3, surface4])
