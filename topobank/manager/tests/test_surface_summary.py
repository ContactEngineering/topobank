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

@pytest.mark.django_db
def test_bandwidth_error_message_when_problems_while_loading():

    #
    # Theoretically loading of a topography can fail during
    # creation of the bandwidth plot, although it worked before.
    # This can happen e.g. because of an update of the PyCo lib
    # which may introduce new errors.
    # In this case the user should see an error message.
    #

    topo1 = TopographyFactory()
    topo2 = TopographyFactory()
    bd = bandwidths_data([topo1, topo2])
    assert len(bd) == 2

    #
    # No errors at first
    #
    bd1, bd2 = bd
    assert bd1['error_message'] is None
    assert bd2['error_message'] is None

    #
    # monkey patch the topography() method of topo1 so we have
    # an exception when trying to egt the pyco topography
    #
    def just_raising_an_exception():
        raise Exception("Cannot load any more.")

    topo1.topography = just_raising_an_exception

    bd = bandwidths_data([topo1, topo2])
    assert len(bd) == 2

    bd1, bd2 = bd

    # first one should indicate that there is an error
    assert bd1['name'] == topo1.name
    assert bd1['error_message'] == f"Topography '{topo1.name}' (id: {topo1.id}) cannot be loaded. " + \
           "Please click to report this issue."
    assert 'Failure loading' in bd1['link']
    assert "id: {}".format(topo1.id) in bd1['link']
    assert bd1['lower_bound'] is None
    assert bd1['upper_bound'] is None

    # second one should be okay (no errors)
    assert bd2['name'] == topo2.name
    assert bd2['error_message'] is None  # No error
    assert bd2['lower_bound'] is not None
    assert bd2['upper_bound'] is not None
