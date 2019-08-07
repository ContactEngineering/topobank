import pytest

from django.db.utils import IntegrityError
from django.db import transaction

from ..models import Topography, Surface
from .utils import two_topos, SurfaceFactory, UserFactory, TopographyFactory

@pytest.mark.django_db
def test_topography_name(two_topos):
    topos = Topography.objects.all().order_by('name')
    assert [ t.name for t in topos ] == ['Example 3 - ZSensor',
                                         'Example 4 - Default']

@pytest.mark.django_db
def test_topography_str(two_topos):
    surface = Surface.objects.get(name="Surface 1")
    topos = Topography.objects.filter(surface=surface).order_by('name')
    assert [ str(t) for t in topos ] == ["Topography 'Example 3 - ZSensor' from 2018-01-01"]

    surface = Surface.objects.get(name="Surface 2")
    topos = Topography.objects.filter(surface=surface).order_by('name')
    assert [str(t) for t in topos] == ["Topography 'Example 4 - Default' from 2018-01-02"]

@pytest.mark.django_db
def test_call_topography_method_multiple_times(two_topos):
    topo = Topography.objects.get(name="Example 3 - ZSensor")

    #
    # coeffs should not change in between calls
    # TODO: probably has to be adjusted to new attribute names in PyCo > 0.5
    #
    pyco_topo = topo.topography()

    # assert isinstance(pyco_topo,

    coeffs_before = pyco_topo.coeffs
    scaling_factor_before = pyco_topo.parent_topography.scale_factor
    pyco_topo = topo.topography()

    assert pyco_topo.parent_topography.scale_factor == scaling_factor_before
    assert pyco_topo.coeffs == coeffs_before



@pytest.mark.django_db
def test_unique_topography_name_in_same_surface():

    user = UserFactory()
    surface1 = SurfaceFactory(creator=user)

    TopographyFactory(surface=surface1, name='TOPO')

    with transaction.atomic(): # otherwise we can't proceed in this test
        with pytest.raises(IntegrityError):
            TopographyFactory(surface=surface1, name='TOPO')

    # no problem with another surface
    surface2 = SurfaceFactory(creator=user)
    TopographyFactory(surface=surface2, name='TOPO')

@pytest.mark.django_db
def test_surface_description(django_user_model):

    username = "testuser"
    password = "abcd$1234"

    user = django_user_model.objects.create_user(username=username, password=password)

    surface = Surface.objects.create(name='Surface 1', creator=user)

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

    surface = SurfaceFactory(creator=user1)

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
    surface = SurfaceFactory(creator=user1)
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










