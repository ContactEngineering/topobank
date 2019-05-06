import pytest

from ..models import Topography, Surface
from .utils import two_topos, SurfaceFactory, UserFactory

@pytest.mark.django_db
def test_topography_name(two_topos):
    topos = Topography.objects.all().order_by('name')
    assert [ t.name for t in topos ] == ['Example 3 - ZSensor',
                                         'Example 4 - Default']

@pytest.mark.django_db
def test_topography_str(two_topos):
    surface = Surface.objects.get(name="Surface 1")
    topos = Topography.objects.filter(surface=surface).order_by('name')
    assert [ str(t) for t in topos ] == ["Topography 'Example 3 - ZSensor' from 2018-01-01",
                                         "Topography 'Example 4 - Default' from 2018-01-02"]

@pytest.mark.django_db
def test_surface_description(django_user_model):

    username = "testuser"
    password = "abcd$1234"

    user = django_user_model.objects.create_user(username=username, password=password)

    surface = Surface.objects.create(name='Surface 1', user=user)

    assert ""==surface.description

    surface.description = "First surface"

    surface.save()

    surface = Surface.objects.get(name='Surface 1')
    assert "First surface" == surface.description

@pytest.mark.django_db
def test_surface_share_and_unshare():

    password = "abcd$1234"

    user1 = UserFactory(password=password)
    user2 = UserFactory(password=password)

    surface = SurfaceFactory(user=user1)

    #
    # no permissions at beginning
    #
    assert not user2.has_perm('view_surface', surface)

    #
    # first: share, but only with view access
    #
    surface.share(user2) # default: only view access
    assert user2.has_perm('view_surface', surface)
    assert not user2.has_perm('change_surface', surface)
    assert not user2.has_perm('delete_surface', surface)
    assert not user2.has_perm('share_surface', surface)

    #
    # second: share, but also with right access
    #
    surface.share(user2, allow_change=True)  # default: only view access
    assert user2.has_perm('view_surface', surface)
    assert user2.has_perm('change_surface', surface)
    assert not user2.has_perm('delete_surface', surface)
    assert not user2.has_perm('share_surface', surface)

    #
    # third: remove all shares again
    #
    surface.unshare(user2)
    assert not user2.has_perm('view_surface', surface)
    assert not user2.has_perm('change_surface', surface)
    assert not user2.has_perm('delete_surface', surface)
    assert not user2.has_perm('share_surface', surface)

    # no problem to call this removal again
    surface.unshare(user2)

@pytest.mark.django_db
def test_other_methods_about_sharing():

    user1 = UserFactory()
    user2 = UserFactory()

    # create surface, at first user 2 has no access
    surface = SurfaceFactory(user=user1)
    assert not surface.is_shared(user2)
    assert not surface.is_shared(user2, allow_change=True)

    # now share and test access
    surface.share(user2)

    assert surface.is_shared(user2)
    assert not surface.is_shared(user2, allow_change=True)

    # .. add permission to change
    surface.share(user2, allow_change=True)
    assert surface.is_shared(user2)
    assert surface.is_shared(user2, allow_change=True)

    # .. remove all permissions
    surface.unshare(user2)
    assert not surface.is_shared(user2)
    assert not surface.is_shared(user2, allow_change=True)










