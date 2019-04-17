import pytest

from ..models import Topography, Surface
from .utils import two_topos

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


