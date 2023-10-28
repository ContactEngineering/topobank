import pytest
from pytest import approx

from dataclasses import dataclass

from django.shortcuts import reverse

from ..models import Topography
from ..utils import bandwidths_data

from .utils import Topography1DFactory, topography_loaded_from_broken_file
from topobank.utils import assert_in_content

@pytest.fixture
def two_topos_mock_for_bandwidth(mocker, db):

    @dataclass  # new feature in Python 3.7
    class STTopoStub:  # ST: from module SurfaceTopography
        bandwidth: tuple
        unit: str
        with_cut_off: bool
        def short_reliability_cutoff(self):
            return 1.2 if self.with_cut_off else None  # should be seen in tests

    topography_method_mock = mocker.patch('topobank.manager.models.Topography.topography')
    topography_method_mock.side_effect = [
        STTopoStub(bandwidth=lambda: (6, 600), unit='nm', with_cut_off=True),
        STTopoStub(bandwidth=lambda: (5, 100), unit='µm', with_cut_off=False),
    ]
    mocker.patch('topobank.manager.models.Topography', autospec=True)

    reverse_patch = mocker.patch('topobank.manager.utils.reverse')
    reverse_patch.side_effect = [
        'linkB/', 'linkA/'
    ]

    # for bandwidths_data():
    #   needed from SurfaceTopography.Topography: pixel_size, size
    #   needed from TopoBank's Topography: name, pk

    topos = [Topography1DFactory(name='topoB', pk=2), Topography1DFactory(name='topoA', pk=1)]

    return topos


def test_bandwidths_data(two_topos_mock_for_bandwidth):

    topoB, topoA = two_topos_mock_for_bandwidth

    for topo in two_topos_mock_for_bandwidth:
        topo.renew_bandwidth_cache()

    bd = bandwidths_data(two_topos_mock_for_bandwidth)

    # expected bandwidth data - smaller lower bounds should be listed first
    exp_bd = [
        dict(upper_bound=6e-7, lower_bound=6e-9, topography=topoB, link='linkB/', short_reliability_cutoff=1.2e-9),
        dict(upper_bound=1e-4, lower_bound=5e-6, topography=topoA, link='linkA/', short_reliability_cutoff=None),
    ]

    for i in range(len(exp_bd)):
        for field in ['upper_bound', 'lower_bound', 'short_reliability_cutoff']:
            assert exp_bd[i][field] == approx(bd[i][field])
        for field in ['topography', 'link']:
            assert exp_bd[i][field] == bd[i][field]


@pytest.mark.django_db
def test_bandwidth_with_angstrom():

    topo = Topography1DFactory(unit='Å')
    bd = bandwidths_data([topo])

    assert len(bd) == 1
