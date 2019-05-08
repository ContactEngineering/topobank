import pytest
from pytest import approx

from dataclasses import dataclass

from ..models import Topography
from ..utils import bandwidths_data

from .utils import TopographyFactory

@pytest.fixture
def two_topos_mock(mocker):

    @dataclass  # new feature in Python 3.7
    class PyCoTopoStub:
        bandwidth: tuple
        info: dict

    topography_method_mock = mocker.patch('topobank.manager.models.Topography.topography')
    topography_method_mock.side_effect = [
        PyCoTopoStub(bandwidth=lambda: (6, 600), info=dict(unit='nm')),
        PyCoTopoStub(bandwidth=lambda: (5, 100), info=dict(unit='µm')),
    ]
    mocker.patch('topobank.manager.models.Topography', autospec=True)

    reverse_patch = mocker.patch('topobank.manager.utils.reverse')
    reverse_patch.side_effect = [
        'linkB/', 'linkA/'
    ]

    # for bandwidths_data():
    #   needed from PyCo's Topography: pixel_size, size
    #   needed from TopoBank's Topography: name, pk

    topos = [Topography(name='topoB', pk=2), Topography(name='topoA', pk=1)]

    return topos

def test_bandwiths_data(two_topos_mock):

    bd = bandwidths_data(two_topos_mock)

    # expected bandwidth data - larger lower bounds should be listed first
    exp_bd = [
        dict(upper_bound=1e-4, lower_bound=5e-6, name='topoA', link='linkA/'),
        dict(upper_bound=6e-7, lower_bound=6e-9, name='topoB', link='linkB/'),
    ]

    for i in range(len(exp_bd)):
        for field in ['upper_bound', 'lower_bound']:
            assert exp_bd[i][field] == approx(bd[i][field])
        for field in ['name', 'link']:
            assert exp_bd[i][field] == bd[i][field]

@pytest.mark.django_db
def test_bandwidth_with_angstrom():

    topo = TopographyFactory(unit='Å')
    bd = bandwidths_data([topo])

    assert len(bd) == 1
