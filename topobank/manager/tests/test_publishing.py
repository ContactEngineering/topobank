import pytest

from .utils import SurfaceFactory


@pytest.mark.django_db
def test_published_field():
    surface = SurfaceFactory()
    assert not surface.is_published
    surface.publish()
    assert surface.is_published
