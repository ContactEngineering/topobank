import numpy as np
import math
import pytest
from dataclasses import dataclass
from numpy.testing import assert_allclose

from SurfaceTopography import Topography, NonuniformLineScan

import topobank.analysis.functions
from topobank.analysis.functions import (
    IncompatibleTopographyException)
from topobank.contact_analysis.functions import contact_mechanics
from topobank.statistical_analysis.functions import height_distribution, slope_distribution, curvature_distribution, \
    power_spectrum, power_spectrum_for_surface, autocorrelation, autocorrelation_for_surface, variable_bandwidth, \
    variable_bandwidth_for_surface, scale_dependent_slope, scale_dependent_slope_for_surface, roughness_parameters

from topobank.manager.tests.utils import SurfaceFactory, Topography1DFactory

EXPECTED_KEYS_FOR_DIST_ANALYSIS = sorted(['name', 'scalars', 'xlabel', 'ylabel', 'xunit', 'yunit', 'series'])
EXPECTED_KEYS_FOR_PLOT_CARD_ANALYSIS = sorted(['alerts', 'name',
                                               'xlabel', 'ylabel', 'xunit', 'yunit',
                                               'xscale', 'yscale', 'series'])

###############################################################################
# Helpers for doing tests
###############################################################################


@dataclass(frozen=True)
class FakeTopographyModel:
    """This model is used to create a Topography for being passed to analysis functions.
    """
    t: Topography
    name: str = "mytopo"
    is_periodic: bool = False

    def topography(self):
        """Return low level topography.
        """
        return self.t

    def get_absolute_url(self):
        return "some/url/"


class DummyProgressRecorder:
    def set_progress(self, a, nsteps):
        """Do nothing."""
        pass  # dummy

###############################################################################
# Tests for line scans
###############################################################################


def test_height_distribution_simple_line_scan():
    x = np.array((1, 2, 3))
    y = 2 * x

    info = dict(unit='nm')

    t = NonuniformLineScan(x, y, info=info).detrend(detrend_mode='center')

    topography = FakeTopographyModel(t)

    result = height_distribution(topography)

    assert sorted(result.keys()) == EXPECTED_KEYS_FOR_DIST_ANALYSIS

    assert result['name'] == 'Height distribution'
    assert result['scalars'] == {
        'Mean Height': {'value': 0, 'unit': 'nm'},
        'RMS Height': {'value': math.sqrt(4. / 3), 'unit': 'nm'},
    }

    assert result['xlabel'] == 'Height'
    assert result['ylabel'] == 'Probability density'
    assert result['xunit'] == 'nm'
    assert result['yunit'] == 'nm⁻¹'

    assert len(result['series']) == 2

    exp_bins = np.array([-1, 1])  # expected values for height bins
    exp_height_dist_values = [1. / 6, 2. / 6]  # expected values
    series0 = result['series'][0]
    np.testing.assert_almost_equal(series0['x'], exp_bins)
    np.testing.assert_almost_equal(series0['y'], exp_height_dist_values)

    # not testing gauss values yet since number of points is unknown
    # proposal: use a well tested function instead of own formula


def test_slope_distribution_simple_line_scan():
    x = np.array((1, 2, 3, 4))
    y = -2 * x

    t = NonuniformLineScan(x, y).detrend(detrend_mode='center')

    topography = FakeTopographyModel(t)

    result = slope_distribution(topography, bins=3)

    assert sorted(result.keys()) == EXPECTED_KEYS_FOR_DIST_ANALYSIS

    assert result['name'] == 'Slope distribution'
    assert result['scalars'] == {
        'Mean Slope (x direction)': dict(value=-2., unit='1'),  # absolute value of slope
        'RMS Slope (x direction)': dict(value=2., unit='1'),  # absolute value of slope
    }

    assert result['xlabel'] == 'Slope'
    assert result['ylabel'] == 'Probability density'
    assert result['xunit'] == '1'
    assert result['yunit'] == '1'

    assert len(result['series']) == 2

    exp_bins = np.array([-2-1/1500, -2, -2+1/1500])  # for slopes
    exp_slope_dist_values = [0, 1500, 0]  # integral with dx=1/3 results to 1
    series0 = result['series'][0]
    np.testing.assert_almost_equal(series0['x'], exp_bins)
    np.testing.assert_almost_equal(series0['y'], exp_slope_dist_values)

    # not testing gauss values yet since number of points is unknown
    # proposal: use a well tested function instead of own formula


def test_curvature_distribution_simple_line_scan():
    unit = 'nm'
    x = np.arange(10)
    y = -2 * x ** 2  # constant curvature

    t = NonuniformLineScan(x, y, info=dict(unit=unit)).detrend(detrend_mode='center')
    topography = FakeTopographyModel(t)

    bins = np.array((-4.75, -4.25, -3.75, -3.25))  # special for this test in order to know results
    result = curvature_distribution(topography, bins=bins)

    assert sorted(result.keys()) == EXPECTED_KEYS_FOR_DIST_ANALYSIS

    assert result['name'] == 'Curvature distribution'

    assert pytest.approx(result['scalars']['Mean Curvature']['value']) == -4
    assert pytest.approx(result['scalars']['RMS Curvature']['value']) == 4
    assert result['scalars']['Mean Curvature']['unit'] == '{}⁻¹'.format(unit)
    assert result['scalars']['RMS Curvature']['unit'] == '{}⁻¹'.format(unit)

    assert result['xlabel'] == 'Curvature'
    assert result['ylabel'] == 'Probability density'
    assert result['xunit'] == '{}⁻¹'.format(unit)
    assert result['yunit'] == unit

    assert len(result['series']) == 2

    exp_bins = (bins[1:] + bins[:-1]) / 2
    exp_curv_dist_values = [0, 2, 0]

    # integral over dx= should be 1
    assert np.trapz(exp_curv_dist_values, exp_bins) == pytest.approx(1)

    series0 = result['series'][0]
    np.testing.assert_almost_equal(series0['x'], exp_bins)
    np.testing.assert_almost_equal(series0['y'], exp_curv_dist_values)

    # not testing gauss values yet since number of points is unknown
    # proposal: use a well tested function instead of own formula


def test_power_spectrum_simple_nonuniform_linescan():
    unit = 'nm'
    x = np.arange(10)
    y = -2 * x ** 2  # constant curvature

    t = NonuniformLineScan(x, y, info=dict(unit=unit)).detrend(detrend_mode='center')
    topography = FakeTopographyModel(t)

    result = power_spectrum(topography)

    assert sorted(result.keys()) == EXPECTED_KEYS_FOR_PLOT_CARD_ANALYSIS

    assert result['name'] == 'Power-spectral density (PSD)'

    assert result['xlabel'] == 'Wavevector'
    assert result['ylabel'] == 'PSD'
    assert result['xunit'] == '{}⁻¹'.format(unit)
    assert result['yunit'] == '{}³'.format(unit)

    assert len(result['series']) == 2

    s0, s1 = result['series']

    assert s0['name'] == '1D PSD along x'
    assert s1['name'] == '1D PSD along x (incl. unreliable data)'

    # TODO Also check values here as integration test?


def test_autocorrelation_simple_nonuniform_topography():
    x = np.arange(5)
    h = 2 * x

    info = dict(unit='nm')

    t = NonuniformLineScan(x, h, info=info).detrend('center')
    topography = FakeTopographyModel(t)

    result = autocorrelation(topography)

    assert sorted(result.keys()) == EXPECTED_KEYS_FOR_PLOT_CARD_ANALYSIS

    assert result['name'] == 'Height-difference autocorrelation function (ACF)'

    # TODO Check result values for autocorrelation


def test_variable_bandwidth_simple_nonuniform_linescan():
    x = np.arange(5)
    h = 2 * x
    info = dict(unit='nm')

    t = NonuniformLineScan(x, h, info=info).detrend('center')
    topography = FakeTopographyModel(t)

    result = variable_bandwidth(topography)

    assert sorted(result.keys()) == EXPECTED_KEYS_FOR_PLOT_CARD_ANALYSIS

    assert result['name'] == 'Variable-bandwidth analysis'
    # TODO Check result values for bandwidth


###############################################################################
# Tests for 2D topographies
###############################################################################


@pytest.fixture
def simple_linear_2d_topography():
    """Simple 2D topography, which is linear in y"""
    unit = 'nm'
    info = dict(unit=unit)
    y = np.arange(10).reshape((1, -1))
    x = np.arange(5).reshape((-1, 1))
    arr = -2 * y + 0 * x  # only slope in y direction
    t = Topography(arr, (5, 10), info=info).detrend('center')
    return t


def test_height_distribution_simple_2d_topography(simple_linear_2d_topography):
    exp_unit = simple_linear_2d_topography.unit
    topography = FakeTopographyModel(simple_linear_2d_topography)
    result = height_distribution(topography, bins=10)

    assert sorted(result.keys()) == EXPECTED_KEYS_FOR_DIST_ANALYSIS

    assert result['name'] == 'Height distribution'

    assert pytest.approx(result['scalars']['Mean Height']['value']) == 0.
    assert pytest.approx(result['scalars']['RMS Height']['value']) == np.sqrt(33)
    assert result['scalars']['Mean Height']['unit'] == exp_unit
    assert result['scalars']['RMS Height']['unit'] == exp_unit

    assert result['xlabel'] == 'Height'
    assert result['ylabel'] == 'Probability density'
    assert result['xunit'] == exp_unit
    assert result['yunit'] == '{}⁻¹'.format(exp_unit)

    assert len(result['series']) == 2

    exp_bins = np.array([-8.1, -6.3, -4.5, -2.7, -0.9, 0.9, 2.7, 4.5, 6.3, 8.1])  # for heights
    exp_height_dist_values = np.ones((10,)) * 1 / (10 * 1.8)  # each interval has width of 1.8, 10 intervals
    series0, series1 = result['series']

    assert series0['name'] == 'Height distribution'

    np.testing.assert_almost_equal(series0['x'], exp_bins)
    np.testing.assert_almost_equal(series0['y'], exp_height_dist_values)

    assert series1['name'] == 'Gaussian fit'
    # TODO not testing gauss values yet since number of points is unknown
    # proposal: use a well tested function instead of own formula


def test_slope_distribution_simple_2d_topography(simple_linear_2d_topography):
    # resulting heights follow this function: h(x,y)=-4y+9
    topography = FakeTopographyModel(simple_linear_2d_topography)
    result = slope_distribution(topography, bins=3)

    assert sorted(result.keys()) == EXPECTED_KEYS_FOR_DIST_ANALYSIS

    assert result['name'] == 'Slope distribution'

    assert pytest.approx(result['scalars']['Mean Slope (x direction)']['value']) == 0.
    assert pytest.approx(result['scalars']['Mean Slope (y direction)']['value']) == -2.
    assert pytest.approx(result['scalars']['RMS Slope (x direction)']['value']) == 0.
    assert pytest.approx(result['scalars']['RMS Slope (y direction)']['value']) == 2.

    for kind, dir in zip(['Mean', 'RMS'], ['x', 'y']):
        assert result['scalars'][f'{kind} Slope ({dir} direction)']['unit'] == '1'

    assert result['xlabel'] == 'Slope'
    assert result['ylabel'] == 'Probability density'
    assert result['xunit'] == '1'
    assert result['yunit'] == '1'

    assert len(result['series']) == 4

    exp_bins_x = np.array([-1. / 1500, 0, 1. / 1500])  # for slopes
    exp_slope_dist_values_x = [0, 1500, 0]
    series0, series1, series2, series3 = result['series']

    assert series0['name'] == 'Slope distribution (x direction)'

    np.testing.assert_almost_equal(series0['x'], exp_bins_x)
    np.testing.assert_almost_equal(series0['y'], exp_slope_dist_values_x)

    exp_bins_y = np.array([-2 - 1. / 1500, -2, -2 + 1. / 1500])  # for slopes
    exp_slope_dist_values_y = [0, 1500, 0]

    assert series1['name'] == 'Gaussian fit (x direction)'

    assert series2['name'] == 'Slope distribution (y direction)'

    np.testing.assert_almost_equal(series2['x'], exp_bins_y)
    np.testing.assert_almost_equal(series2['y'], exp_slope_dist_values_y)

    assert series3['name'] == 'Gaussian fit (y direction)'
    # TODO not testing gauss values yet since number of points is unknown
    # proposal: use a well tested function instead of own formula


def test_curvature_distribution_simple_2d_topography(simple_linear_2d_topography):
    unit = simple_linear_2d_topography.unit
    # resulting heights follow this function: h(x,y)=-4y+9

    topography = FakeTopographyModel(simple_linear_2d_topography)
    result = curvature_distribution(topography, bins=3)

    assert sorted(result.keys()) == EXPECTED_KEYS_FOR_DIST_ANALYSIS

    assert result['name'] == 'Curvature distribution'

    assert pytest.approx(result['scalars']['Mean Curvature']['value']) == 0.
    assert pytest.approx(result['scalars']['RMS Curvature']['value']) == 0.
    assert result['scalars']['Mean Curvature']['unit'] == '{}⁻¹'.format(unit)
    assert result['scalars']['RMS Curvature']['unit'] == '{}⁻¹'.format(unit)

    assert result['xlabel'] == 'Curvature'
    assert result['ylabel'] == 'Probability density'
    assert result['xunit'] == '{}⁻¹'.format(unit)
    assert result['yunit'] == unit

    assert len(result['series']) == 2

    s0, s1 = result['series']

    exp_bins = np.array([-1. / 1500, 0, 1. / 1500])  # for curvatures
    exp_curvature_dist_values = [0, 1500, 0]

    assert s0['name'] == 'Curvature distribution'

    np.testing.assert_almost_equal(s0['x'], exp_bins)
    np.testing.assert_almost_equal(s0['y'], exp_curvature_dist_values)

    assert s1['name'] == 'Gaussian fit'
    # Not further testing gaussian here


def test_curvature_distribution_simple_2d_topography_periodic():
    unit = 'nm'
    info = dict(unit=unit)

    y = np.arange(100).reshape((1, -1))

    arr = np.sin(y / 2 / np.pi)  # only slope in y direction, second derivative is -sin

    t = Topography(arr, (100, 100), periodic=True, info=info).detrend('center')
    # resulting heights follow this function: h(x,y)=-2y+9

    topography = FakeTopographyModel(t)
    result = curvature_distribution(topography, bins=3)

    assert sorted(result.keys()) == EXPECTED_KEYS_FOR_DIST_ANALYSIS

    assert result['name'] == 'Curvature distribution'

    assert pytest.approx(result['scalars']['Mean Curvature']['value']) == 0.
    assert result['scalars']['Mean Curvature']['unit'] == '{}⁻¹'.format(unit)


def test_power_spectrum_simple_2d_topography(simple_linear_2d_topography):
    unit = simple_linear_2d_topography.unit
    # resulting heights follow this function: h(x,y)=-2y+9

    topography = FakeTopographyModel(simple_linear_2d_topography)
    result = power_spectrum(topography)

    assert sorted(result.keys()) == EXPECTED_KEYS_FOR_PLOT_CARD_ANALYSIS

    assert result['name'] == 'Power-spectral density (PSD)'

    assert result['xlabel'] == 'Wavevector'
    assert result['ylabel'] == 'PSD'
    assert result['xunit'] == '{}⁻¹'.format(unit)
    assert result['yunit'] == '{}³'.format(unit)

    assert len(result['series']) == 6

    s0, s1, s2, s3, s4, s5 = result['series']

    assert s0['name'] == '1D PSD along x'
    assert s1['name'] == '1D PSD along y'
    assert s2['name'] == 'q/π × 2D PSD'
    assert s3['name'] == '1D PSD along x (incl. unreliable data)'
    assert s4['name'] == '1D PSD along y (incl. unreliable data)'
    assert s5['name'] == 'q/π × 2D PSD (incl. unreliable data)'

    # TODO Also check values here as integration test?


def test_autocorrelation_simple_2d_topography(simple_linear_2d_topography):
    # resulting heights follow this function: h(x,y)=-2y+9
    topography = FakeTopographyModel(simple_linear_2d_topography)
    result = autocorrelation(topography)

    assert sorted(result.keys()) == EXPECTED_KEYS_FOR_PLOT_CARD_ANALYSIS

    assert result['name'] == 'Height-difference autocorrelation function (ACF)'

    # TODO Check result values for autocorrelation


def test_scale_dependent_slope_simple_2d_topography(simple_linear_2d_topography):
    # resulting heights follow this function: h(x,y)=-2y+9
    topography = FakeTopographyModel(simple_linear_2d_topography)
    result = scale_dependent_slope(topography)

    assert sorted(result.keys()) == EXPECTED_KEYS_FOR_PLOT_CARD_ANALYSIS

    assert result['name'] == 'Scale-dependent slope'
    for dataset in result['series']:
        if dataset['name'] == 'Along y':
            np.testing.assert_almost_equal(dataset['y'], 2*np.ones_like(dataset['y']))


def test_variable_bandwidth_simple_2d_topography(simple_linear_2d_topography):
    topography = FakeTopographyModel(simple_linear_2d_topography)
    result = variable_bandwidth(topography)

    assert sorted(result.keys()) == EXPECTED_KEYS_FOR_PLOT_CARD_ANALYSIS

    assert result['name'] == 'Variable-bandwidth analysis'
    # TODO Check result values for bandwidth


def test_contact_mechanics_incompatible_topography():
    x = np.arange(10)
    arr = 2 * x
    info = dict(unit='nm')
    t = NonuniformLineScan(x, arr, info=info).detrend("center")
    topography = FakeTopographyModel(t)

    with pytest.raises(IncompatibleTopographyException):
        contact_mechanics(topography)


def test_contact_mechanics_whether_given_pressures_in_result(simple_linear_2d_topography):

    given_pressures = [2e-3, 1e-2]
    topography = FakeTopographyModel(simple_linear_2d_topography)
    result = contact_mechanics(topography,
                               nsteps=None, pressures=given_pressures, storage_prefix='test/',
                               progress_recorder=DummyProgressRecorder())

    np.testing.assert_almost_equal(result['mean_pressures'], given_pressures)


@pytest.mark.parametrize('periodic', [True, False])
def test_contact_mechanics_effective_kwargs_in_result(periodic):
    y = np.arange(10).reshape((1, -1))
    x = np.arange(5).reshape((-1, 1))

    arr = -2 * y + 0 * x  # only slope in y direction

    info = dict(unit='nm')
    t = Topography(arr, (10, 5), info=info, periodic=periodic).detrend('center')

    topography = FakeTopographyModel(t)
    result = contact_mechanics(topography, substrate_str=None, nsteps=10, storage_prefix='test/',
                               progress_recorder=DummyProgressRecorder())

    exp_effective_kwargs = dict(
        substrate_str=('' if periodic else 'non') + 'periodic',
        nsteps=10,
        pressures=None,
        hardness=None,
        maxiter=100,
    )
    assert result['effective_kwargs'] == exp_effective_kwargs


def test_roughness_parameters(simple_linear_2d_topography):
    unit = simple_linear_2d_topography.unit
    inverse_unit = '{}⁻¹'.format(unit)
    topography = FakeTopographyModel(simple_linear_2d_topography)
    result = roughness_parameters(topography)

    expected = [
        {
            'quantity': 'RMS height',
            'direction': 'x',
            'from': 'profile (1D)',
            'symbol': 'Rq',
            'value': 0,
            'unit': unit
        },
        {
            'quantity': 'RMS height',
            'direction': 'y',
            'from': 'profile (1D)',
            'symbol': 'Rq',
            'value': 5.74456264,
            'unit': unit
        },
        {
            'quantity': 'RMS height',
            'direction': None,
            'from': 'area (2D)',
            'symbol': 'Sq',
            'value': np.sqrt(33),
            'unit': unit
        },
        {
            'quantity': 'RMS curvature',
            'direction': 'y',
            'from': 'profile (1D)',
            'symbol': '',
            'value': 0,
            'unit': inverse_unit,
        },
        {
            'quantity': 'RMS curvature',
            'direction': None,
            'from': 'area (2D)',
            'symbol': '',
            'value': 0,
            'unit': inverse_unit,
        },
        {
            'quantity': 'RMS curvature',
            'direction': 'x',
            'from': 'profile (1D)',
            'symbol': '',
            'value': 0,
            'unit': inverse_unit,
        },
        {
            'quantity': 'RMS slope',
            'direction': 'x',
            'from': 'profile (1D)',
            'symbol': 'R&Delta;q',
            'value': 0,
            'unit': 1,
        },
        {
            'quantity': 'RMS slope',
            'direction': 'y',
            'from': 'profile (1D)',
            'symbol': 'R&Delta;q',
            'value': 2,
            'unit': 1,
        },
        {
            'quantity': 'RMS gradient',
            'direction': None,
            'from': 'area (2D)',
            'symbol': '',
            'value': 2,
            'unit': 1,
        },
        {
            'quantity': 'Bandwidth: lower bound',
            'direction': None,
            'from': 'area (2D)',
            'symbol': '',
            'value': 1.0,
            'unit': unit,
        },
        {
            'quantity': 'Bandwidth: upper bound',
            'direction': None,
            'from': 'area (2D)',
            'symbol': '',
            'value': 7.5,
            'unit': unit,
        },
    ]

    # Look whether all fields are included
    assert len(result) == len(expected)

    # compare all fields in detail
    for exp, actual in zip(expected, result):
        assert_allclose(exp['value'], actual['value'],
                        atol=1e-14,
                        err_msg=f"Different values: exp: {exp}, actual: {actual}")
        del exp['value']
        del actual['value']
        assert exp == actual


###############################################################################
# Testing analysis functions for surfaces
###############################################################################


@pytest.fixture
def simple_surface():
    class WrapTopography:
        def __init__(self, t):
            self._t = t
        def topography(self):
            return self._t

    class WrapRequest:
        def __init__(self, c):
            self._c = c
        def all(self):
            return self._c

    class WrapSurface:
        def __init__(self, c):
            self._c = c
        @property
        def topography_set(self):
            return WrapRequest(self._c)

    nx, ny = 113, 123
    sx, sy = 1, 1
    lx = 0.3
    topographies = [
        Topography(np.resize(np.sin(np.arange(nx) * sx * 2 * np.pi / (nx * lx)), (nx, ny)), (sx, sy), periodic=False,
                   unit='um')
    ]

    nx = 278
    sx = 100
    lx = 2
    x = np.arange(nx) * sx / nx
    topographies += [
        NonuniformLineScan(x, np.cos(x * np.pi / lx), unit='nm')
    ]

    return WrapSurface([WrapTopography(t) for t in topographies])


def test_psd_for_surface(simple_surface):
    """Testing PSD for an artificial surface."""

    result = power_spectrum_for_surface(simple_surface, nb_points_per_decade=3)

    expected_result = {
        'name': 'Power-spectral density (PSD)',
        'xlabel': 'Wavevector',
        'ylabel': 'PSD',
        'xunit': 'nm⁻¹',
        'yunit': 'nm³',
        'xscale': 'log',
        'yscale': 'log',
        'series': [
            {
                'name': '1D PSD along x',
                # This is a pure regression test
                'x': [6.283185e-03, 1.503970e-02, 3.281944e-02, 6.922845e-02,
                      1.589340e-01, 3.147830e-01, 7.102774e-01, 1.576467e+00,
                      3.436698e+00, 7.409395e+00, 1.380985e+01],
                'y': [8.380153e+05, 1.444988e+05, 9.826013e+04, 3.596532e+05,
                      5.352438e+06, 1.219130e+06, 2.709713e-08, 1.241935e+00,
                      4.943693e-09, 4.544197e-13, 1.752703e-05],
            }
        ],
        'alerts': [],
    }

    for k in ['name', 'xunit', 'yunit', 'xlabel', 'ylabel', 'xscale', 'yscale']:
        assert expected_result[k] == result[k]

    assert expected_result['series'][0]['name'] == result['series'][0]['name']
    assert_allclose(expected_result['series'][0]['x'], result['series'][0]['x'], rtol=1e-6)
    assert_allclose(expected_result['series'][0]['y'], result['series'][0]['y'], rtol=1e-6)


def test_autocorrelation_for_surface(simple_surface):
    """Testing autocorrelation for an artificial surface."""

    result = autocorrelation_for_surface(simple_surface, nb_points_per_decade=3)

    expected_result = {
        'name': 'Height-difference autocorrelation function (ACF)',
        'xlabel': 'Distance',
        'ylabel': 'ACF',
        'xunit': 'nm',
        'yunit': 'nm²',
        'xscale': 'log',
        'yscale': 'log',
        'series': [
            {
                'name': 'Along x',
                # This is a pure regression test
                'x': [3.237410e-01, 7.194245e-01, 1.492413, 3.247700,
                      8.111829, 1.683517e+01, 3.496530e+01, 7.431925e+01,
                      1.592920e+02, 3.451327e+02, 7.345133e+02],
                'y': [6.372497e-02, 2.788402e-01, 7.872059e-01, 3.479716e-01,
                      2.909510e+05, 4.353897e+05, 2.104788e+05, 2.454415e+05,
                      5.123730e+05, 4.951154e+05, 5.092170e+05],
            }
        ]
    }

    for k in ['name', 'xunit', 'yunit', 'xlabel', 'ylabel', 'xscale', 'yscale']:
        assert expected_result[k] == result[k]

    assert expected_result['series'][0]['name'] == result['series'][0]['name']
    assert_allclose(expected_result['series'][0]['x'], result['series'][0]['x'], rtol=1e-6)
    assert_allclose(expected_result['series'][0]['y'], result['series'][0]['y'], rtol=1e-6)


def test_variable_bandwidth_for_surface(simple_surface):
    """Testing variable bandwidth for an artificial surface."""

    result = variable_bandwidth_for_surface(simple_surface, nb_points_per_decade=3)

    expected_result = {
        'name': 'Variable-bandwidth analysis',
        'xlabel': 'Bandwidth',
        'ylabel': 'RMS height',
        'xunit': 'nm',
        'yunit': 'nm',
        'xscale': 'log',
        'yscale': 'log',
        'series': [
            {
                'name': 'Profile decomposition along x',
                # This is a pure regression test
                'x': [3.892199e-01, 7.784397e-01, 1.556879, 3.113759,
                      6.227518, 1.342703e+01, 2.808543e+01, 6.861511e+01,
                      1.250000e+02, 2.500000e+02, 7.500000e+02],
                'y': [9.832030e-03, 3.501679e-02, 1.304232e-01, 4.237846e-01,
                      6.662862e-01, 6.774048e-01, 6.856179e-01, 3.342818e+02,
                      7.008752e+02, 7.070114e+02, 7.083317e+02],
            }
        ]
    }

    for k in ['name', 'xunit', 'yunit', 'xlabel', 'ylabel', 'xscale', 'yscale']:
        assert expected_result[k] == result[k]

    assert expected_result['series'][0]['name'] == result['series'][0]['name']
    assert_allclose(expected_result['series'][0]['x'], result['series'][0]['x'], rtol=1e-6)
    assert_allclose(expected_result['series'][0]['y'], result['series'][0]['y'], rtol=1e-6)


def test_scale_dependent_slope_for_surface(simple_surface):
    """Testing scale-dependent slope for an artificial surface."""

    result = scale_dependent_slope_for_surface(simple_surface, nb_points_per_decade=3)

    expected_result = {
        'name': 'Scale-dependent slope',
        'xlabel': 'Distance',
        'ylabel': 'Slope',
        'xunit': 'nm',
        'yunit': '1',
        'xscale': 'log',
        'yscale': 'log',
        'series': [
            {
                'name': 'Slope in x-direction',
                # This is a pure regression test
                'x': [0.464159, 1., 2.154435, 4.641589, 10., 21.544347, 46.415888, 100., 215.443469, 464.158883],
                'y': [1.060357, 0.975031, 0.633874, 0.143609, 74.384165, 33.003073, 16.146693, 2.761759, 5.296848,
                      1.332137],
            }
        ]
    }

    for k in ['name', 'xunit', 'yunit', 'xlabel', 'ylabel', 'xscale', 'yscale']:
        assert expected_result[k] == result[k]

    assert expected_result['series'][0]['name'] == result['series'][0]['name']
    assert_allclose(expected_result['series'][0]['x'], result['series'][0]['x'], atol=1e-6)
    assert_allclose(expected_result['series'][0]['y'], result['series'][0]['y'], atol=1e-6)


@pytest.mark.parametrize(["x_dim", "y_dim"], [[20000, 10000], [9999999, 3]])
def test_exception_topography_too_large_for_contact_mechanics(x_dim, y_dim, mocker, simple_linear_2d_topography):
    topo = FakeTopographyModel(simple_linear_2d_topography)

    # patch raw topography in order to return a higher number of grid points
    m = mocker.patch("SurfaceTopography.Topography.nb_grid_pts", new_callable=mocker.PropertyMock)
    m.return_value = (x_dim, y_dim)  # this make the topography returning high numbers of grid points

    with pytest.raises(IncompatibleTopographyException):
        contact_mechanics(topo, storage_prefix='test')


@pytest.mark.parametrize(["topo_is_periodic", "substrate_str", "exp_num_alerts"], [
    [False, 'nonperiodic', 0],
    [False, 'periodic', 1],
    [True, 'nonperiodic', 1],
    [True, 'periodic', 0],
])
def test_alert_if_topographys_periodicity_does_not_match(simple_linear_2d_topography,
                                                         topo_is_periodic, substrate_str, exp_num_alerts):
    topo = FakeTopographyModel(simple_linear_2d_topography, is_periodic=topo_is_periodic)
    result = contact_mechanics(topo, substrate_str=substrate_str, storage_prefix='test',
                               progress_recorder=DummyProgressRecorder())
    assert len(result['alerts']) == exp_num_alerts
