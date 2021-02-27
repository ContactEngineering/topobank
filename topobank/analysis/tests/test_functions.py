import numpy as np
import math
import pytest
from dataclasses import dataclass
from numpy.testing import assert_allclose

from SurfaceTopography import Topography, NonuniformLineScan

from topobank.analysis.functions import (
    IncompatibleTopographyException,
    height_distribution, slope_distribution, curvature_distribution,
    power_spectrum, autocorrelation, variable_bandwidth,
    contact_mechanics, rms_values,
    average_series_list, power_spectrum_for_surface)

from topobank.manager.tests.utils import SurfaceFactory, TopographyFactory

###############################################################################
# Helpers for doing tests
###############################################################################

@dataclass(frozen=True)
class FakeTopographyModel:
    """This model is used to create a Topography for being passed to analysis functions.
    """
    t: Topography

    def topography(self):
        """Return low level topography.
        """
        return self.t


###############################################################################
# Tests for line scans
###############################################################################


def test_height_distribution_simple_line_scan():

    x = np.array((1,2,3))
    y = 2*x

    info = dict(unit='nm')

    t = NonuniformLineScan(x,y,info=info).detrend(detrend_mode='center')

    topography = FakeTopographyModel(t)

    result = height_distribution(topography)

    assert list(result.keys()) == ['name', 'scalars', 'xlabel', 'ylabel', 'xunit', 'yunit', 'series']

    assert result['name'] == 'Height distribution'
    assert result['scalars'] == {
            'Mean Height': {'value': 0,               'unit': 'nm'},
            'RMS Height':  {'value': math.sqrt(4./3), 'unit': 'nm'},
    }

    assert result['xlabel'] == 'Height'
    assert result['ylabel'] == 'Probability'
    assert result['xunit'] == 'nm'
    assert result['yunit'] == 'nm⁻¹'

    assert len(result['series']) == 2

    exp_bins = np.array([-1, 1]) # expected values for height bins
    exp_height_dist_values = [1./6,2./6] # expected values
    series0 = result['series'][0]
    np.testing.assert_almost_equal(series0['x'], exp_bins)
    np.testing.assert_almost_equal(series0['y'], exp_height_dist_values)

    # not testing gauss values yet since number of points is unknown
    # proposal: use a well tested function instead of own formula


def test_slope_distribution_simple_line_scan():

    x = np.array((1,2,3,4))
    y = -2*x

    t = NonuniformLineScan(x, y).detrend(detrend_mode='center')

    topography = FakeTopographyModel(t)

    result = slope_distribution(topography, bins=3)

    assert sorted(result.keys()) == sorted(['name', 'scalars', 'xlabel', 'ylabel', 'xunit', 'yunit', 'series'])

    assert result['name'] == 'Slope distribution'
    assert result['scalars'] == {
            'Mean Slope (x direction)': dict(value=-2., unit='1'),  # absolute value of slope
            'RMS Slope (x direction)':  dict(value=2., unit='1'),   # absolute value of slope
    }

    assert result['xlabel'] == 'Slope'
    assert result['ylabel'] == 'Probability'
    assert result['xunit'] == '1'
    assert result['yunit'] == '1'

    assert len(result['series']) == 2

    exp_bins = np.array([-2.33333333333, -2, -1.66666666666])  # for slopes
    exp_slope_dist_values = [0, 3, 0]  # integral with dx=1/3 results to 1
    series0 = result['series'][0]
    np.testing.assert_almost_equal(series0['x'], exp_bins)
    np.testing.assert_almost_equal(series0['y'], exp_slope_dist_values)

    # not testing gauss values yet since number of points is unknown
    # proposal: use a well tested function instead of own formula


def test_curvature_distribution_simple_line_scan():

    unit = 'nm'
    x = np.arange(10)
    y = -2*x**2 # constant curvature

    t = NonuniformLineScan(x, y, info=dict(unit=unit)).detrend(detrend_mode='center')
    topography = FakeTopographyModel(t)

    bins = np.array((-4.75,-4.25,-3.75,-3.25)) # special for this test in order to know results
    result = curvature_distribution(topography, bins=bins)

    assert sorted(result.keys()) == sorted(['name', 'scalars', 'xlabel', 'ylabel', 'xunit', 'yunit', 'series'])

    assert result['name'] == 'Curvature distribution'

    assert pytest.approx(result['scalars']['Mean Curvature']['value']) == -4
    assert pytest.approx(result['scalars']['RMS Curvature']['value']) == 4
    assert result['scalars']['Mean Curvature']['unit'] == '{}⁻¹'.format(unit)
    assert result['scalars']['RMS Curvature']['unit'] == '{}⁻¹'.format(unit)

    assert result['xlabel'] == 'Curvature'
    assert result['ylabel'] == 'Probability'
    assert result['xunit'] == '{}⁻¹'.format(unit)
    assert result['yunit'] == unit

    assert len(result['series']) == 2

    exp_bins = (bins[1:]+bins[:-1])/2
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
    y = -2*x**2 # constant curvature

    t = NonuniformLineScan(x, y, info=dict(unit=unit)).detrend(detrend_mode='center')
    topography = FakeTopographyModel(t)

    result = power_spectrum(topography)

    assert sorted(result.keys()) == sorted(['name', 'xlabel', 'ylabel', 'xunit', 'yunit', 'xscale', 'yscale', 'series'])

    assert result['name'] == 'Power-spectral density (PSD)'

    assert result['xlabel'] == 'Wavevector'
    assert result['ylabel'] == 'PSD'
    assert result['xunit'] == '{}⁻¹'.format(unit)
    assert result['yunit'] == '{}³'.format(unit)

    assert len(result['series']) == 1

    s0, = result['series']

    assert s0['name'] == '1D PSD along x'

    # TODO Also check values here as integration test?


def test_autocorrelation_simple_nonuniform_topography():

    x = np.arange(5)
    h = 2*x

    info = dict(unit='nm')

    t = NonuniformLineScan(x, h, info=info).detrend('center')
    topography = FakeTopographyModel(t)

    result = autocorrelation(topography)

    assert sorted(result.keys()) == sorted(['name', 'xlabel', 'ylabel', 'xscale', 'yscale', 'xunit', 'yunit', 'series'])

    assert result['name'] == 'Height-difference autocorrelation function (ACF)'

    # TODO Check result values for autocorrelation


def test_variable_bandwidth_simple_nonuniform_linescan():

    x = np.arange(5)
    h = 2 * x
    info = dict(unit='nm')

    t = NonuniformLineScan(x, h, info=info).detrend('center')
    topography = FakeTopographyModel(t)

    result = variable_bandwidth(topography)

    assert sorted(result.keys()) == sorted(['name', 'xlabel', 'ylabel', 'xscale', 'yscale', 'xunit', 'yunit', 'series'])

    assert result['name'] == 'Variable-bandwidth analysis'
    # TODO Check result values for bandwidth


###############################################################################
# Tests for 2D topographies
###############################################################################


@pytest.fixture
def simple_2d_topography():
    unit = 'nm'
    info = dict(unit=unit)

    y = np.arange(10).reshape((1, -1))
    x = np.arange(5).reshape((-1, 1))

    arr = -2 * y + 0 * x  # only slope in y direction

    t = Topography(arr, (10, 5), info=info).detrend('center')

    return t


def test_height_distribution_simple_2d_topography(simple_2d_topography):

    exp_unit = simple_2d_topography.info['unit']
    topography = FakeTopographyModel(simple_2d_topography)
    result = height_distribution(topography, bins=10)

    assert sorted(result.keys()) == sorted(['name', 'scalars', 'xlabel', 'ylabel', 'xunit', 'yunit', 'series'])

    assert result['name'] == 'Height distribution'

    assert pytest.approx(result['scalars']['Mean Height']['value']) == 0.
    assert pytest.approx(result['scalars']['RMS Height']['value']) == np.sqrt(33)
    assert result['scalars']['Mean Height']['unit'] == exp_unit
    assert result['scalars']['RMS Height']['unit'] == exp_unit

    assert result['xlabel'] == 'Height'
    assert result['ylabel'] == 'Probability'
    assert result['xunit'] == exp_unit
    assert result['yunit'] == '{}⁻¹'.format(exp_unit)

    assert len(result['series']) == 2

    exp_bins = np.array([-8.1, -6.3, -4.5, -2.7, -0.9,  0.9,  2.7,  4.5,  6.3,  8.1])  # for heights
    exp_height_dist_values = np.ones((10,))*1/(10*1.8)  # each interval has width of 1.8, 10 intervals
    series0 = result['series'][0]

    assert series0['name'] == 'Height distribution'

    np.testing.assert_almost_equal(series0['x'], exp_bins)
    np.testing.assert_almost_equal(series0['y'], exp_height_dist_values)

    # TODO not testing gauss values yet since number of points is unknown
    # proposal: use a well tested function instead of own formula


def test_slope_distribution_simple_2d_topography(simple_2d_topography):

    # resulting heights follow this function: h(x,y)=-4y+9
    topography = FakeTopographyModel(simple_2d_topography)
    result = slope_distribution(topography, bins=3)

    assert sorted(result.keys()) == sorted(['name', 'scalars', 'xlabel', 'ylabel', 'xunit', 'yunit', 'series'])

    assert result['name'] == 'Slope distribution'

    assert pytest.approx(result['scalars']['Mean Slope (x direction)']['value']) == 0.
    assert pytest.approx(result['scalars']['Mean Slope (y direction)']['value']) == -4.
    assert pytest.approx(result['scalars']['RMS Slope (x direction)']['value']) == 0.
    assert pytest.approx(result['scalars']['RMS Slope (y direction)']['value']) == 4.

    for kind, dir in zip(['Mean', 'RMS'], ['x', 'y']):
        assert result['scalars'][f'{kind} Slope ({dir} direction)']['unit'] == '1'

    assert result['xlabel'] == 'Slope'
    assert result['ylabel'] == 'Probability'
    assert result['xunit'] == '1'
    assert result['yunit'] == '1'

    assert len(result['series']) == 4

    exp_bins_x = np.array([-1./3, 0, 1./3]) # for slopes
    exp_slope_dist_values_x = [0, 3, 0]
    series0 = result['series'][0]

    assert series0['name'] == 'Slope distribution (x direction)'

    np.testing.assert_almost_equal(series0['x'], exp_bins_x)
    np.testing.assert_almost_equal(series0['y'], exp_slope_dist_values_x)

    exp_bins_y = np.array([-4-1. / 3, -4, -4+1. / 3])  # for slopes
    exp_slope_dist_values_y = [0, 3, 0]
    series2 = result['series'][2]

    assert series2['name'] == 'Slope distribution (y direction)'

    np.testing.assert_almost_equal(series2['x'], exp_bins_y)
    np.testing.assert_almost_equal(series2['y'], exp_slope_dist_values_y)

    # TODO not testing gauss values yet since number of points is unknown
    # proposal: use a well tested function instead of own formula


def test_curvature_distribution_simple_2d_topography(simple_2d_topography):

    unit = simple_2d_topography.info['unit']
    # resulting heights follow this function: h(x,y)=-4y+9

    topography = FakeTopographyModel(simple_2d_topography)
    result = curvature_distribution(topography, bins=3)

    assert sorted(result.keys()) == sorted(['name', 'scalars', 'xlabel', 'ylabel', 'xunit', 'yunit', 'series'])

    assert result['name'] == 'Curvature distribution'

    assert pytest.approx(result['scalars']['Mean Curvature']['value']) == 0.
    assert pytest.approx(result['scalars']['RMS Curvature']['value']) == 0.
    assert result['scalars']['Mean Curvature']['unit'] == '{}⁻¹'.format(unit)
    assert result['scalars']['RMS Curvature']['unit'] == '{}⁻¹'.format(unit)

    assert result['xlabel'] == 'Curvature'
    assert result['ylabel'] == 'Probability'
    assert result['xunit'] == '{}⁻¹'.format(unit)
    assert result['yunit'] == unit

    assert len(result['series']) == 2

    s0, s1 = result['series']

    exp_bins = np.array([-1./3, 0, 1./3]) # for curvatures
    exp_curvature_dist_values = [0, 3, 0]

    assert s0['name'] == 'Curvature distribution'

    np.testing.assert_almost_equal(s0['x'], exp_bins)
    np.testing.assert_almost_equal(s0['y'], exp_curvature_dist_values)

    assert s1['name'] == 'RMS curvature'
    # Not testing gaussian here

def test_curvature_distribution_simple_2d_topography_periodic():

    unit = 'nm'
    info = dict(unit=unit)

    y = np.arange(100).reshape((1, -1))

    arr = np.sin(y/2/np.pi) # only slope in y direction, second derivative is -sin

    t = Topography(arr, (100,100), periodic=True, info=info).detrend('center')
    # resulting heights follow this function: h(x,y)=-4y+9

    topography = FakeTopographyModel(t)
    result = curvature_distribution(topography, bins=3)

    assert sorted(result.keys()) == sorted(['name', 'scalars', 'xlabel', 'ylabel', 'xunit', 'yunit', 'series'])

    assert result['name'] == 'Curvature distribution'

    assert pytest.approx(result['scalars']['Mean Curvature']['value']) == 0.
    assert result['scalars']['Mean Curvature']['unit'] == '{}⁻¹'.format(unit)


def test_power_spectrum_simple_2d_topography(simple_2d_topography):

    unit = simple_2d_topography.info['unit']
    # resulting heights follow this function: h(x,y)=-4y+9

    topography = FakeTopographyModel(simple_2d_topography)
    result = power_spectrum(topography)

    assert sorted(result.keys()) == sorted(['name', 'xlabel', 'ylabel', 'xunit', 'yunit', 'xscale', 'yscale', 'series'])

    assert result['name'] == 'Power-spectral density (PSD)'

    assert result['xlabel'] == 'Wavevector'
    assert result['ylabel'] == 'PSD'
    assert result['xunit'] == '{}⁻¹'.format(unit)
    assert result['yunit'] == '{}³'.format(unit)

    assert len(result['series']) == 3

    s0, s1, s2 = result['series']

    assert s0['name'] == 'q/π × 2D PSD'
    assert s1['name'] == '1D PSD along x'
    assert s2['name'] == '1D PSD along y'

    # TODO Also check values here as integration test?


def test_autocorrelation_simple_2d_topography(simple_2d_topography):

    # resulting heights follow this function: h(x,y)=-4y+9
    topography = FakeTopographyModel(simple_2d_topography)
    result = autocorrelation(topography)

    assert sorted(result.keys()) == sorted(['name', 'xlabel', 'ylabel', 'xscale', 'yscale', 'xunit', 'yunit', 'series'])

    assert result['name'] == 'Height-difference autocorrelation function (ACF)'

    # TODO Check result values for autocorrelation


def test_variable_bandwidth_simple_2d_topography(simple_2d_topography):

    topography = FakeTopographyModel(simple_2d_topography)
    result = variable_bandwidth(topography)

    assert sorted(result.keys()) == sorted(['name', 'xlabel', 'ylabel', 'xscale', 'yscale', 'xunit', 'yunit', 'series'])

    assert result['name'] == 'Variable-bandwidth analysis'
    # TODO Check result values for bandwidth


def test_contact_mechanics_incompatible_topography():

    x = np.arange(10)
    arr = 2*x
    info = dict(unit='nm')
    t = NonuniformLineScan(x,arr, info=info).detrend("center")
    topography = FakeTopographyModel(t)

    with pytest.raises(IncompatibleTopographyException):
        contact_mechanics(topography)


def test_contact_mechanics_whether_given_pressures_in_result(simple_2d_topography):

    class ProgressRecorder:
        def set_progress(self, a, nsteps):
            pass  # dummy

    given_pressures = [2e-3, 1e-2]
    topography = FakeTopographyModel(simple_2d_topography)
    result = contact_mechanics(topography,
                               nsteps=None, pressures=given_pressures, storage_prefix='test/',
                               progress_recorder=ProgressRecorder())

    np.testing.assert_almost_equal(result['mean_pressures'], given_pressures)


@pytest.mark.parametrize('periodic', [True, False])
def test_contact_mechanics_effective_kwargs_in_result(periodic):

    y = np.arange(10).reshape((1, -1))
    x = np.arange(5).reshape((-1, 1))

    arr = -2 * y + 0 * x  # only slope in y direction

    info = dict(unit='nm')
    t = Topography(arr, (10, 5), info=info, periodic=periodic).detrend('center')

    class ProgressRecorder:
        def set_progress(self, a, nsteps):
            pass  # dummy

    topography = FakeTopographyModel(t)
    result = contact_mechanics(topography, nsteps=10, storage_prefix='test/',
                               progress_recorder=ProgressRecorder())

    exp_effective_kwargs = dict(
        substrate_str=('' if periodic else 'non')+'periodic',
        nsteps=10,
        pressures=None,
        hardness=None,
        maxiter=100,
    )
    assert result['effective_kwargs'] == exp_effective_kwargs


def test_rms_values(simple_2d_topography):

    unit = simple_2d_topography.info['unit']
    inverse_unit = '{}⁻¹'.format(unit)
    topography = FakeTopographyModel(simple_2d_topography)
    result = rms_values(topography)

    assert result == [
        {
            'quantity': 'RMS Height',
            'direction': None,
            'value': np.sqrt(33),
            'unit': unit,
        },
        {
            'quantity': 'RMS Curvature',
            'direction': None,
            'value': 0,
            'unit': inverse_unit,
        },
        {
            'quantity': 'RMS Slope',
            'direction': 'x',
            'value': 0,
            'unit': 1,
        },
        {
            'quantity': 'RMS Slope',
            'direction': 'y',
            'value': 4,
            'unit': 1,
        }
    ]

###############################################################################
# Testing analysis functions for surfaces
###############################################################################


def test_average_series_list_linear_scale():
    """Testing the helper function 'average_series_list' for linear scale."""
    series_list = [
        {
            'name': 'quantity',  # taken from y=x
            'x': np.array([1, 2, 3, 5, 6, 7]),
            'y': np.array([1, 2, 3, 5, 6, 7]),
        },
        {
            'name': 'quantity',  # taken from y=2*x
            'x': np.array([0, 1.5, 2.5, 5]),
            'y': np.array([0, 3, 5, 10]),
        }
    ]

    expected_average_series = {
        'name': 'quantity',
        'x': np.linspace(0, 7, 15),  # 0, 0.5, ..., 6.5, 7
        'y': np.array([0, 1, 1.5, 9/4, 3, 15/4, 9/2, 21/4, 6, 27/4, 30/4, 5.5, 6, 6.5, 7]),
        'std_err_y': np.array([0, 0, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2, 2.25, 2.5, 0, 0, 0, 0])
    }

    result = average_series_list(series_list, num_points=15)

    assert result['name'] == expected_average_series['name']
    assert_allclose(result['x'], expected_average_series['x'])
    assert_allclose(result['y'], expected_average_series['y'])
    assert_allclose(result['std_err_y'], expected_average_series['std_err_y'])


def test_average_series_list_loglog_scale():
    """Testing the helper function 'average_series_list' for loglog scale."""
    series_list = [
        {
            'name': 'quantity',  # taken from y=x
            'x': np.exp([1, 2, 3, 5, 6, 7]),
            'y': np.exp([1, 2, 3, 5, 6, 7]),
        },
        {
            'name': 'quantity',  # taken from y=2*x
            'x': np.exp([0, 1.5, 2.5, 5]),
            'y': np.exp([0, 3, 5, 10]),
        }
    ]

    expected_average_series = {
        'name': 'quantity',
        'x': np.exp(np.linspace(0, 7, 15)),  # 0, 0.5, ..., 6.5, 7
        'y': np.exp([0, 1, 1.5, 9/4, 3, 15/4, 9/2, 21/4, 6, 27/4, 30/4, 5.5, 6, 6.5, 7]),
        'std_err_y': np.exp([0, 0, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2, 2.25, 2.5, 0, 0, 0, 0])
    }

    result = average_series_list(series_list, num_points=15, xscale='log', yscale='log')

    assert result['name'] == expected_average_series['name']
    assert_allclose(result['x'], expected_average_series['x'])
    assert_allclose(result['y'], expected_average_series['y'])
    assert_allclose(result['std_err_y'], expected_average_series['std_err_y'])


@pytest.mark.django_db
def test_psd_for_surface(mocker):
    """Testing PSD for an artificial surface."""

    # PSD results for individual topographies are mocked up
    topo1_result = dict(
        name='Power-spectral density (PSD)',
        xlabel='Wavevector',
        ylabel='PSD',
        xunit='µm⁻¹',
        yunit='µm³',
        xscale='log',
        yscale='log',
        series=[
            {
                'name': 'PSD',  # taken from y=x
                'x': np.exp([0.9, 2, 3, 5, 6, 7]),
                'y': np.exp([0.9, 2, 3, 5, 6, 7]),
                # using here 0.9 instead of 1 so we can clearly
                # interpolate at 1.0, otherwise with (1,1) there is no
                # interpolation at 1.0 due to numerical errors (exp->log..)
            },
        ]
    )
    topo2_result = dict(
        name='Power-spectral density (PSD)',
        xlabel='Wavevector',
        ylabel='PSD',
        xunit='nm⁻¹',  # nm instead of µm
        yunit='nm³',
        xscale='log',
        yscale='log',
        series=[
            {
                'name': 'PSD',  # taken from y=2*x
                'x': 1e-3*np.exp([0, 1.5, 2.5, 5.0]),   # small numbers because of xunit=nm⁻¹ compared to xunit=µm⁻¹
                'y': 1e9*np.exp([0, 3, 5, 10]),  # very small numbers because nm³->µm³
            }  # the numbers are scaled here in order to match the units of first topography + reuse known results
        ]
    )

    power_spectrum_mock = mocker.patch('topobank.analysis.functions.power_spectrum',
                                       side_effect=[topo1_result, topo2_result])

    surf = SurfaceFactory()
    topo1 = TopographyFactory(surface=surf)  # we just need 2 topographies
    topo2 = TopographyFactory(surface=surf)

    result = power_spectrum_for_surface(surf, num_points=15)

    expected_result = {
        'name': 'Power-spectral density (PSD)',
        'xlabel': 'Wavevector',
        'ylabel': 'PSD',
        'xunit': 'µm⁻¹',
        'yunit': 'µm³',
        'xscale': 'log',
        'yscale': 'log',
        'series': [
            {
                'x': np.exp(np.linspace(0, 7, 15)),  # 0.5, ..., 6.5, 7 in plot
                'y': np.exp([0, 1, 1.5, 9 / 4, 3, 15 / 4, 9 / 2, 21 / 4, 6, 27 / 4, 30 / 4, 5.5, 6, 6.5, 7]),
                'std_err_y': np.exp([0, 0, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2, 2.25, 2.5, 0, 0, 0, 0])
            }
        ]
    }

    for k in ['name', 'xunit', 'yunit', 'xlabel', 'ylabel', 'xscale', 'yscale']:
        assert expected_result[k] == result[k]

    assert_allclose(expected_result['series'][0]['x'], result['series'][0]['x'])
    assert_allclose(expected_result['series'][0]['y'], result['series'][0]['y'])
    assert_allclose(expected_result['series'][0]['std_err_y'], result['series'][0]['std_err_y'])


