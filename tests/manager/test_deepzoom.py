import pytest

from topobank.testing.factories import Topography2DFactory


@pytest.mark.django_db
def test_deepzoom_creation_fails(mocker):
    topo = Topography2DFactory(size_x=1, size_y=1)
    topo.refresh_cache()
    # should have a deepzoom images
    assert topo.deepzoom is not None

    mocker.patch(
        "topobank.manager.models.Topography._make_deepzoom",
        side_effect=Exception("Test exception"),
    )
    topo.refresh_cache()
    # should have no deepzoom images
    assert topo.deepzoom is None
