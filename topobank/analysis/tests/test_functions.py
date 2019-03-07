import numpy as np
import math
import pytest

from PyCo.Topography import Topography, NonuniformLineScan

from topobank.analysis.functions import (
    height_distribution, slope_distribution, curvature_distribution,
    autocorrelation, variable_bandwidth)

###############################################################################
# Tests for line scans
###############################################################################

def test_height_distribution_simple_line_scan():

    x = np.array((1,2,3))
    y = 2*x

    info = dict(unit='nm')

    t = NonuniformLineScan(x,y,info=info).detrend(detrend_mode='center')

    result = height_distribution(t)

    assert list(result.keys()) == ['name', 'scalars', 'xlabel', 'ylabel', 'xunit', 'yunit', 'series']

    assert result['name'] == 'Height distribution'
    assert result['scalars'] == {
            'Mean Height': 0,
            'RMS Height': math.sqrt(4./3),
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

    result = slope_distribution(t, bins=3)

    assert sorted(result.keys()) == sorted(['name', 'scalars', 'xlabel', 'ylabel', 'xunit', 'yunit', 'series'])

    assert result['name'] == 'Slope distribution'
    assert result['scalars'] == {
            'Mean Slope (x direction)': -2.,  # absolut value of slope
            'RMS Slope (x direction)': 2., # absolut value of slope
    }

    assert result['xlabel'] == 'Slope'
    assert result['ylabel'] == 'Probability'
    assert result['xunit'] == '1'
    assert result['yunit'] == '1'

    assert len(result['series']) == 2

    exp_bins = np.array([-2.33333333333, -2, -1.66666666666]) # for slopes
    exp_slope_dist_values = [0, 3, 0] # integral with dx=1/3 results to 1
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

    bins = np.array((-4.75,-4.25,-3.75,-3.25)) # special for this test in order to know results
    result = curvature_distribution(t, bins=bins)

    assert sorted(result.keys()) == sorted(['name', 'scalars', 'xlabel', 'ylabel', 'xunit', 'yunit', 'series'])

    assert result['name'] == 'Curvature distribution'

    assert pytest.approx(result['scalars']['Mean Curvature']) == -4
    assert pytest.approx(result['scalars']['RMS Curvature']) == 4

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

###############################################################################
# Tests for 2D topographies
###############################################################################

def test_slope_distribution_simple_2D_topography():

    y = np.arange(10).reshape((1, -1))
    x = np.arange(5).reshape((-1, 1))

    arr = -2*y+0*x # only slope in y direction

    t = Topography(arr, (10,5)).detrend('center')

    # resulting heights follow this function: h(x,y)=-4y+9

    result = slope_distribution(t, bins=3)

    assert sorted(result.keys()) == sorted(['name', 'scalars', 'xlabel', 'ylabel', 'xunit', 'yunit', 'series'])

    assert result['name'] == 'Slope distribution'

    assert pytest.approx(result['scalars']['Mean Slope (x direction)']) == 0.
    assert pytest.approx(result['scalars']['Mean Slope (y direction)']) == -4.
    assert pytest.approx(result['scalars']['RMS Slope (x direction)']) == 0.
    assert pytest.approx(result['scalars']['RMS Slope (y direction)']) == 4.

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

def test_autocorrelation_simple_2D_topography():
    y = np.arange(10).reshape((1, -1))
    x = np.arange(5).reshape((-1, 1))

    arr = -2 * y + 0 * x  # only slope in y direction
    info = dict(unit='nm')

    t = Topography(arr, (10, 5), info=info).detrend('center')

    # resulting heights follow this function: h(x,y)=-4y+9

    result = autocorrelation(t)

    assert sorted(result.keys()) == sorted(['name', 'xlabel', 'ylabel', 'xscale', 'yscale', 'xunit', 'yunit', 'series'])

    assert result['name'] == 'Height-difference autocorrelation function (ACF)'

    # TODO Check result values for autocorrelation

def test_variable_bandwidth_simple_2D_topography():
    y = np.arange(10).reshape((1, -1))
    x = np.arange(5).reshape((-1, 1))

    arr = -2 * y + 0 * x  # only slope in y direction

    info = dict(unit='nm')
    t = Topography(arr, (10, 5), info=info).detrend('center')

    # resulting heights follow this function: h(x,y)=-4y+9

    result = variable_bandwidth(t)

    assert sorted(result.keys()) == sorted(['name', 'xlabel', 'ylabel', 'xscale', 'yscale', 'xunit', 'yunit', 'series'])

    assert result['name'] == 'Variable-bandwidth analysis'
    # TODO Check result values for bandwidht

def test_autocorrelation_simple_nonuniform_topography():

    x = np.arange(5)
    h = 2*x

    info = dict(unit='nm')

    t = NonuniformLineScan(x, h, info=info).detrend('center')

    result = autocorrelation(t)

    assert sorted(result.keys()) == sorted(['name', 'xlabel', 'ylabel', 'xscale', 'yscale', 'xunit', 'yunit', 'series'])

    assert result['name'] == 'Height-difference autocorrelation function (ACF)'

    # TODO Check result values for autocorrelation

def test_variable_bandwidth_simple_nonuniform_linescan():

    x = np.arange(5)
    h = 2 * x
    info = dict(unit='nm')

    t = NonuniformLineScan(x, h, info=info).detrend('center')

    result = variable_bandwidth(t)

    assert sorted(result.keys()) == sorted(['name', 'xlabel', 'ylabel', 'xscale', 'yscale', 'xunit', 'yunit', 'series'])

    assert result['name'] == 'Variable-bandwidth analysis'
    # TODO Check result values for bandwidht
