import numpy as np
import math
import pytest
from dataclasses import dataclass
from numpy.testing import assert_allclose

from SurfaceTopography import Topography, NonuniformLineScan

from topobank.analysis.functions import (
    IncompatibleTopographyException,
    height_distribution, slope_distribution, curvature_distribution,
    power_spectrum, autocorrelation, scale_dependent_slope, variable_bandwidth,
    contact_mechanics, rms_values,
    average_series_list,
    power_spectrum_for_surface, autocorrelation_for_surface, scale_dependent_slope_for_surface,
    variable_bandwidth_for_surface)

from topobank.manager.tests.utils import SurfaceFactory, Topography1DFactory


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
    x = np.array((1, 2, 3))
    y = 2 * x

    info = dict(unit='nm')

    t = NonuniformLineScan(x, y, info=info).detrend(detrend_mode='center')

    topography = FakeTopographyModel(t)

    result = height_distribution(topography)

    assert list(result.keys()) == ['name', 'scalars', 'xlabel', 'ylabel', 'xunit', 'yunit', 'series']

    assert result['name'] == 'Height distribution'
    assert result['scalars'] == {
        'Mean Height': {'value': 0, 'unit': 'nm'},
        'RMS Height': {'value': math.sqrt(4. / 3), 'unit': 'nm'},
    }

    assert result['xlabel'] == 'Height'
    assert result['ylabel'] == 'Probability'
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

    assert sorted(result.keys()) == sorted(['name', 'scalars', 'xlabel', 'ylabel', 'xunit', 'yunit', 'series'])

    assert result['name'] == 'Slope distribution'
    assert result['scalars'] == {
        'Mean Slope (x direction)': dict(value=-2., unit='1'),  # absolute value of slope
        'RMS Slope (x direction)': dict(value=2., unit='1'),  # absolute value of slope
    }

    assert result['xlabel'] == 'Slope'
    assert result['ylabel'] == 'Probability'
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
    h = 2 * x

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
    exp_unit = simple_linear_2d_topography.info['unit']
    topography = FakeTopographyModel(simple_linear_2d_topography)
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

    exp_bins = np.array([-8.1, -6.3, -4.5, -2.7, -0.9, 0.9, 2.7, 4.5, 6.3, 8.1])  # for heights
    exp_height_dist_values = np.ones((10,)) * 1 / (10 * 1.8)  # each interval has width of 1.8, 10 intervals
    series0 = result['series'][0]

    assert series0['name'] == 'Height distribution'

    np.testing.assert_almost_equal(series0['x'], exp_bins)
    np.testing.assert_almost_equal(series0['y'], exp_height_dist_values)

    # TODO not testing gauss values yet since number of points is unknown
    # proposal: use a well tested function instead of own formula


def test_slope_distribution_simple_2d_topography(simple_linear_2d_topography):
    # resulting heights follow this function: h(x,y)=-4y+9
    topography = FakeTopographyModel(simple_linear_2d_topography)
    result = slope_distribution(topography, bins=3)

    assert sorted(result.keys()) == sorted(['name', 'scalars', 'xlabel', 'ylabel', 'xunit', 'yunit', 'series'])

    assert result['name'] == 'Slope distribution'

    assert pytest.approx(result['scalars']['Mean Slope (x direction)']['value']) == 0.
    assert pytest.approx(result['scalars']['Mean Slope (y direction)']['value']) == -2.
    assert pytest.approx(result['scalars']['RMS Slope (x direction)']['value']) == 0.
    assert pytest.approx(result['scalars']['RMS Slope (y direction)']['value']) == 2.

    for kind, dir in zip(['Mean', 'RMS'], ['x', 'y']):
        assert result['scalars'][f'{kind} Slope ({dir} direction)']['unit'] == '1'

    assert result['xlabel'] == 'Slope'
    assert result['ylabel'] == 'Probability'
    assert result['xunit'] == '1'
    assert result['yunit'] == '1'

    assert len(result['series']) == 4

    exp_bins_x = np.array([-1. / 1500, 0, 1. / 1500])  # for slopes
    exp_slope_dist_values_x = [0, 1500, 0]
    series0 = result['series'][0]

    assert series0['name'] == 'Slope distribution (x direction)'

    np.testing.assert_almost_equal(series0['x'], exp_bins_x)
    np.testing.assert_almost_equal(series0['y'], exp_slope_dist_values_x)

    exp_bins_y = np.array([-2 - 1. / 1500, -2, -2 + 1. / 1500])  # for slopes
    exp_slope_dist_values_y = [0, 1500, 0]
    series2 = result['series'][2]

    assert series2['name'] == 'Slope distribution (y direction)'

    np.testing.assert_almost_equal(series2['x'], exp_bins_y)
    np.testing.assert_almost_equal(series2['y'], exp_slope_dist_values_y)

    # TODO not testing gauss values yet since number of points is unknown
    # proposal: use a well tested function instead of own formula


def test_curvature_distribution_simple_2d_topography(simple_linear_2d_topography):
    unit = simple_linear_2d_topography.info['unit']
    # resulting heights follow this function: h(x,y)=-4y+9

    topography = FakeTopographyModel(simple_linear_2d_topography)
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

    exp_bins = np.array([-1. / 1500, 0, 1. / 1500])  # for curvatures
    exp_curvature_dist_values = [0, 1500, 0]

    assert s0['name'] == 'Curvature distribution'

    np.testing.assert_almost_equal(s0['x'], exp_bins)
    np.testing.assert_almost_equal(s0['y'], exp_curvature_dist_values)

    assert s1['name'] == 'RMS curvature'
    # Not testing gaussian here


def test_curvature_distribution_simple_2d_topography_periodic():
    unit = 'nm'
    info = dict(unit=unit)

    y = np.arange(100).reshape((1, -1))

    arr = np.sin(y / 2 / np.pi)  # only slope in y direction, second derivative is -sin

    t = Topography(arr, (100, 100), periodic=True, info=info).detrend('center')
    # resulting heights follow this function: h(x,y)=-2y+9

    topography = FakeTopographyModel(t)
    result = curvature_distribution(topography, bins=3)

    assert sorted(result.keys()) == sorted(['name', 'scalars', 'xlabel', 'ylabel', 'xunit', 'yunit', 'series'])

    assert result['name'] == 'Curvature distribution'

    assert pytest.approx(result['scalars']['Mean Curvature']['value']) == 0.
    assert result['scalars']['Mean Curvature']['unit'] == '{}⁻¹'.format(unit)


def test_power_spectrum_simple_2d_topography(simple_linear_2d_topography):
    unit = simple_linear_2d_topography.info['unit']
    # resulting heights follow this function: h(x,y)=-2y+9

    topography = FakeTopographyModel(simple_linear_2d_topography)
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


def test_autocorrelation_simple_2d_topography(simple_linear_2d_topography):
    # resulting heights follow this function: h(x,y)=-2y+9
    topography = FakeTopographyModel(simple_linear_2d_topography)
    result = autocorrelation(topography)

    assert sorted(result.keys()) == sorted(['name', 'xlabel', 'ylabel', 'xscale', 'yscale', 'xunit', 'yunit', 'series'])

    assert result['name'] == 'Height-difference autocorrelation function (ACF)'

    # TODO Check result values for autocorrelation


def test_scale_dependent_slope_simple_2d_topography(simple_linear_2d_topography):
    # resulting heights follow this function: h(x,y)=-2y+9
    topography = FakeTopographyModel(simple_linear_2d_topography)
    result = scale_dependent_slope(topography)

    assert sorted(result.keys()) == sorted(['name', 'xlabel', 'ylabel', 'xscale', 'yscale', 'xunit', 'yunit', 'series'])

    assert result['name'] == 'Scale-dependent slope'
    for dataset in result['series']:
        if dataset['name'] == 'Along y':
            np.testing.assert_almost_equal(dataset['y'], 2*np.ones_like(dataset['y']))


def test_variable_bandwidth_simple_2d_topography(simple_linear_2d_topography):
    topography = FakeTopographyModel(simple_linear_2d_topography)
    result = variable_bandwidth(topography)

    assert sorted(result.keys()) == sorted(['name', 'xlabel', 'ylabel', 'xscale', 'yscale', 'xunit', 'yunit', 'series'])

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
    class ProgressRecorder:
        def set_progress(self, a, nsteps):
            pass  # dummy

    given_pressures = [2e-3, 1e-2]
    topography = FakeTopographyModel(simple_linear_2d_topography)
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
        substrate_str=('' if periodic else 'non') + 'periodic',
        nsteps=10,
        pressures=None,
        hardness=None,
        maxiter=100,
    )
    assert result['effective_kwargs'] == exp_effective_kwargs


def test_rms_values(simple_linear_2d_topography):
    unit = simple_linear_2d_topography.info['unit']
    inverse_unit = '{}⁻¹'.format(unit)
    topography = FakeTopographyModel(simple_linear_2d_topography)
    result = rms_values(topography)

    assert result[0]['quantity'] == 'RMS Height'
    assert result[0]['direction'] is None
    assert np.isclose(result[0]['value'], np.sqrt(33))
    assert result[0]['unit'] == unit

    assert result[1]['quantity'] == 'RMS Curvature'
    assert result[1]['direction'] is None
    assert np.isclose(result[1]['value'], 0)
    assert result[1]['unit'] == inverse_unit

    assert result[2]['quantity'] == 'RMS Slope'
    assert result[2]['direction'] == 'x'
    assert np.isclose(result[2]['value'], 0)
    assert result[2]['unit'] == 1

    assert result[3]['quantity'] == 'RMS Slope'
    assert result[3]['direction'] == 'y'
    assert np.isclose(result[3]['value'], 2)
    assert result[3]['unit'] == 1


###############################################################################
# Testing analysis functions for surfaces
###############################################################################


def _expected(xscale):
    """Returns tuple with expected (x,y,std_err_y)"""
    if xscale == 'log':
        expected_x = np.geomspace(0.1, 7, 15)
    else:
        expected_x = np.linspace(0.1, 7, 15)

    expected_y = np.piecewise(expected_x,
                              [expected_x < 1, (expected_x >= 1) & (expected_x <= 5), expected_x > 5],
                              [lambda x: 2 * x, lambda x: 3 * x / 2, lambda x: x])
    expected_std_err_y = np.piecewise(
        expected_x,
        [expected_x < 1, (expected_x >= 1) & (expected_x <= 5), expected_x > 5],
        [np.nan, lambda x: np.abs(x) / 2, np.nan])
    return expected_x, expected_y, expected_std_err_y


@pytest.mark.parametrize('xscale', ['linear', 'log'])
def test_average_series_list_linear_scale(xscale):
    """Testing the helper function 'average_series_list' for linear scale."""
    series_list = [
        {
            'name': 'quantity',  # taken from y=x
            'x': np.array([1, 2, 3, 5, 6, 7]),
            'y': np.array([1, 2, 3, 5, 6, 7]),
        },
        {
            'name': 'quantity',  # taken from y=2*x
            'x': np.array([0.1, 1.5, 2.5, 5]),
            'y': np.array([0.2, 3, 5, 10]),
        }
    ]

    # if case of xscale == 'log', add some negative values
    # in order to see whether they will be filtered out:
    if xscale == 'log':
        for dim in ['x', 'y']:
            series_list[0][dim] = np.concatenate([(-1,), series_list[0][dim]])

    expected_x, expected_y, expected_std_err_y = _expected(xscale)

    expected_average_series = {
        'name': 'quantity',
        'x': expected_x,
        'y': expected_y,
        'std_err_y': expected_std_err_y
    }

    result = average_series_list(series_list, num_points=15, xscale=xscale)

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
                'name': '1D',  # taken from y=x
                'x': np.array([1, 2, 3, 5, 6, 7]),
                'y': np.array([1, 2, 3, 5, 6, 7]),
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
                'name': '1D',  # taken from y=2*x
                'x': 1e-3 * np.array([0.1, 1.5, 2.5, 5.0]),
                # small numbers because of xunit=nm⁻¹ compared to xunit=µm⁻¹
                'y': 1e9 * np.array([0.2, 3, 5, 10]),  # very small numbers because nm³->µm³
            }  # the numbers are scaled here in order to match the units of first topography + reuse known results
        ]
    )

    power_spectrum_mock = mocker.patch('topobank.analysis.functions.power_spectrum',
                                       side_effect=[topo1_result, topo2_result])

    surf = SurfaceFactory()
    topo1 = Topography1DFactory(surface=surf)  # we just need 2 topographies
    topo2 = Topography1DFactory(surface=surf)

    result = power_spectrum_for_surface(surf, num_points=15)

    expected_x, expected_y, expected_std_err_y = _expected('log')

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
                'name': '1D',
                'x': expected_x,
                'y': expected_y,
                'std_err_y': expected_std_err_y
            }
        ]
    }

    for k in ['name', 'xunit', 'yunit', 'xlabel', 'ylabel', 'xscale', 'yscale']:
        assert expected_result[k] == result[k]

    assert expected_result['series'][0]['name'] == result['series'][0]['name']
    assert_allclose(expected_result['series'][0]['x'], result['series'][0]['x'])
    assert_allclose(expected_result['series'][0]['y'], result['series'][0]['y'])
    assert_allclose(expected_result['series'][0]['std_err_y'], result['series'][0]['std_err_y'])


@pytest.mark.django_db
def test_autocorrelation_for_surface(mocker):
    """Testing autocorrelation for an artificial surface."""

    # ACF results for individual topographies are mocked up
    topo1_result = dict(
        name='Height-difference autocorrelation function (ACF)',
        xlabel='Distance',
        ylabel='ACF',
        xunit='µm',
        yunit='µm²',
        xscale='log',
        yscale='log',
        series=[
            {
                'name': '1D',  # taken from y=x
                'x': np.array([1, 2, 3, 5, 6, 7]),
                'y': np.array([1, 2, 3, 5, 6, 7]),
            },
        ]
    )
    topo2_result = dict(
        name='Height-difference autocorrelation function (ACF)',
        xlabel='Distance',
        ylabel='ACF',
        xunit='nm',  # nm instead of µm
        yunit='nm²',
        xscale='log',
        yscale='log',
        series=[
            {
                'name': '1D',  # taken from y=2*x
                'x': 1e3 * np.array([0.1, 1.5, 2.5, 5.0]),  # large numbers because of xunit=nm compared to xunit=µm
                'y': 1e6 * np.array([0.2, 3, 5, 10]),  # larger numbers because nm²->µm²
            }  # the numbers are scaled here in order to match the units of first topography + reuse known results
        ]
    )

    autocorrelation_mock = mocker.patch('topobank.analysis.functions.autocorrelation',
                                        side_effect=[topo1_result, topo2_result])

    surf = SurfaceFactory()
    topo1 = Topography1DFactory(surface=surf)  # we just need 2 topographies
    topo2 = Topography1DFactory(surface=surf)

    result = autocorrelation_for_surface(surf, num_points=15)

    expected_x, expected_y, expected_std_err_y = _expected('log')

    expected_result = {
        'name': 'Height-difference autocorrelation function (ACF)',
        'xlabel': 'Distance',
        'ylabel': 'ACF',
        'xunit': 'µm',
        'yunit': 'µm²',
        'xscale': 'log',
        'yscale': 'log',
        'series': [
            {
                'name': '1D',
                'x': expected_x,
                'y': expected_y,
                'std_err_y': expected_std_err_y
            }
        ]
    }

    for k in ['name', 'xunit', 'yunit', 'xlabel', 'ylabel', 'xscale', 'yscale']:
        assert expected_result[k] == result[k]

    assert expected_result['series'][0]['name'] == result['series'][0]['name']
    assert_allclose(expected_result['series'][0]['x'], result['series'][0]['x'])
    assert_allclose(expected_result['series'][0]['y'], result['series'][0]['y'])
    assert_allclose(expected_result['series'][0]['std_err_y'], result['series'][0]['std_err_y'])


@pytest.mark.django_db
def test_scale_dependent_slope_for_surface(mocker):
    """Testing autocorrelation for an artificial surface."""

    # ACF results for individual topographies are mocked up
    topo1_result = dict(
        name='Scale-dependent Slope',
        xlabel='Distance',
        ylabel='Slope',
        xunit='µm',
        yunit='1',
        xscale='log',
        yscale='log',
        series=[
            {
                'name': '1D',  # taken from y=x
                'x': np.array([1, 2, 3, 5, 6, 7]),
                'y': np.array([1, 2, 3, 5, 6, 7]),
            },
        ]
    )
    topo2_result = dict(
        name='Scale-dependent Slope',
        xlabel='Distance',
        ylabel='Slope',
        xunit='nm',  # nm instead of µm
        yunit='1',
        xscale='log',
        yscale='log',
        series=[
            {
                'name': '1D',  # taken from y=2*x
                'x': 1e3 * np.array([0.1, 1.5, 2.5, 5.0]),  # large numbers because of xunit=nm compared to xunit=µm
                'y': np.array([0.2, 3, 5, 10]),  # no conversion of y-data (because it is a slope)
            }  # the numbers are scaled here in order to match the units of first topography + reuse known results
        ]
    )

    scale_dependent_slope_mock = mocker.patch('topobank.analysis.functions.scale_dependent_slope',
                                              side_effect=[topo1_result, topo2_result])

    surf = SurfaceFactory()
    topo1 = Topography1DFactory(surface=surf)  # we just need 2 topographies
    topo2 = Topography1DFactory(surface=surf)

    result = scale_dependent_slope_for_surface(surf, num_points=15)

    expected_x, expected_y, expected_std_err_y = _expected('log')

    expected_result = {
        'name': 'Scale-dependent Slope',
        'xlabel': 'Distance',
        'ylabel': 'Slope',
        'xunit': 'µm',
        'yunit': '1',
        'xscale': 'log',
        'yscale': 'log',
        'series': [
            {
                'name': '1D',
                'x': expected_x,
                'y': expected_y,
                'std_err_y': expected_std_err_y
            }
        ]
    }

    for k in ['name', 'xunit', 'yunit', 'xlabel', 'ylabel', 'xscale', 'yscale']:
        assert expected_result[k] == result[k]

    assert expected_result['series'][0]['name'] == result['series'][0]['name']
    assert_allclose(expected_result['series'][0]['x'], result['series'][0]['x'])
    assert_allclose(expected_result['series'][0]['y'], result['series'][0]['y'])
    assert_allclose(expected_result['series'][0]['std_err_y'], result['series'][0]['std_err_y'])


@pytest.mark.django_db
def test_variable_bandwidth_for_surface(mocker):
    """Testing variable bandwidth for an artificial surface."""

    # ACF results for individual topographies are mocked up
    topo1_result = dict(
        name='Variable-bandwidth analysis',
        xlabel='Bandwidth',
        ylabel='RMS Height',
        xunit='µm',
        yunit='µm',
        xscale='log',
        yscale='log',
        series=[
            {
                'name': 'VBM',  # taken from y=x
                'x': np.array([1, 2, 3, 5, 6, 7]),
                'y': np.array([1, 2, 3, 5, 6, 7]),
            },
        ]
    )
    topo2_result = dict(
        name='Variable-bandwidth analysis',
        xlabel='Bandwidth',
        ylabel='RMS Height',
        xunit='nm',  # nm instead of µm
        yunit='nm',
        xscale='log',
        yscale='log',
        series=[
            {
                'name': 'VBM',  # taken from y=2*x
                'x': 1e3 * np.array([0.1, 1.5, 2.5, 5.0]),  # large numbers because of xunit=nm compared to xunit=µm
                'y': 1e3 * np.array([0.2, 3, 5, 10]),  # large numbers because of yunit=nm compared to yunit=µm
            }  # the numbers are scaled here in order to match the units of first topography + reuse known results
        ]
    )

    vbm_mock = mocker.patch('topobank.analysis.functions.variable_bandwidth',
                            side_effect=[topo1_result, topo2_result])

    surf = SurfaceFactory()
    topo1 = Topography1DFactory(surface=surf)  # we just need 2 topographies
    topo2 = Topography1DFactory(surface=surf)

    result = variable_bandwidth_for_surface(surf, num_points=15)

    expected_x, expected_y, expected_std_err_y = _expected('log')

    expected_result = {
        'name': 'Variable-bandwidth analysis',
        'xlabel': 'Bandwidth',
        'ylabel': 'RMS Height',
        'xunit': 'µm',
        'yunit': 'µm',
        'xscale': 'log',
        'yscale': 'log',
        'series': [
            {
                'name': 'VBM',
                'x': expected_x,
                'y': expected_y,
                'std_err_y': expected_std_err_y
            }
        ]
    }

    for k in ['name', 'xunit', 'yunit', 'xlabel', 'ylabel', 'xscale', 'yscale']:
        assert expected_result[k] == result[k]

    assert expected_result['series'][0]['name'] == result['series'][0]['name']
    assert_allclose(expected_result['series'][0]['x'], result['series'][0]['x'])
    assert_allclose(expected_result['series'][0]['y'], result['series'][0]['y'])
    assert_allclose(expected_result['series'][0]['std_err_y'], result['series'][0]['std_err_y'])
