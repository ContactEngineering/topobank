import pytest

from ..models import Topography
from .utils import two_topos

@pytest.mark.django_db
def test_topography_name(two_topos):
    topos = Topography.objects.all().order_by('name')
    assert [ t.name for t in topos ] == ['surface1', 'surface2']

@pytest.mark.django_db
def test_topography_str(two_topos):
    topos = Topography.objects.all().order_by('name')
    assert [ str(t) for t in topos ] == ["Topography 'surface1' from 2018-01-01",
                                         "Topography 'surface2' from 2018-07-01"]
