import pytest
from pytest import approx

from dataclasses import dataclass

from ..models import Topography
from ..utils import bandwidths_data


@pytest.fixture
def two_topos_mock(mocker):

    @dataclass  # new feature in Python 3.7
    class PyCoTopoStub:
        pixel_size: float
        size: float
        unit: str

    topography_method_mock = mocker.patch('topobank.manager.models.Topography.topography')
    topography_method_mock.side_effect = [
        PyCoTopoStub(pixel_size=5., size=100., unit='µm'),
        PyCoTopoStub(pixel_size=6., size=600., unit='nm'),
    ]
    mocker.patch('topobank.manager.models.Topography', autospec=True)

    reverse_patch = mocker.patch('topobank.manager.utils.reverse')
    reverse_patch.side_effect = [
        'linkA/', 'linkB/'
    ]

    # for bandwidths_data():
    #   needed from PyCo's Topography: pixel_size, size
    #   needed from TopoBank's Topography: name, pk

    topos = [Topography(name='topoA', pk=1), Topography(name='topoB', pk=2)]

    return topos

def test_bandwiths_data(two_topos_mock):

    bd = bandwidths_data(two_topos_mock)

    exp_bd = [
        dict(upper_bound=1e-4, lower_bound=5e-6, name='topoA', link='linkA/'),
        dict(upper_bound=6e-7, lower_bound=6e-9, name='topoB', link='linkB/'),
    ]

    for i in [0,1]:
        for field in ['upper_bound', 'lower_bound']:
            assert exp_bd[i][field] == approx(bd[i][field])
        for field in ['name', 'link']:
            assert exp_bd[i][field] == bd[i][field]

