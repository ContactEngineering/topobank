from PyCo.Topography import NonuniformNumpyTopography
from PyCo.Topography.TopographyPipeline import DetrendedTopography, ScaledTopography
import numpy as np
import math

from topobank.analysis.functions import height_distribution, slope_distribution

def test_height_distribution_simple_line_scan():

    x = np.array((1,2,3))
    y = 2*x
    t = DetrendedTopography(ScaledTopography(NonuniformNumpyTopography(x=x, y=y, unit='nm'), 1),
                            detrend_mode='center') # only substract mean value

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

    exp_bins = np.array([-1, 1]) # for heights
    exp_height_dist_values = [1./6,2./6]
    series0 = result['series'][0]
    np.testing.assert_almost_equal(series0['x'], exp_bins)
    np.testing.assert_almost_equal(series0['y'], exp_height_dist_values)

    # TODO not really testing gauss values yet since number of points is unknown
    # proposal: use a well tested function instead of own formula

def test_slope_distribution_simple_line_scan():

    x = np.array((1,2,3,4))
    y = -2*x
    t = DetrendedTopography(ScaledTopography(NonuniformNumpyTopography(x=x, y=y, unit='nm'), 1),
                            detrend_mode='center') # only substract mean value

    result = slope_distribution(t, bins=3)

    assert list(result.keys()) == ['name', 'scalars', 'xlabel', 'ylabel', 'xunit', 'yunit', 'series']

    assert result['name'] == 'Slope distribution'
    assert result['scalars'] == {
            'Mean Slope': -2.,
            'RMS Slope': 2., # absolut value of slope
    }

    assert result['xlabel'] == 'Slope'
    assert result['ylabel'] == 'Probability'
    assert result['xunit'] == '1'
    assert result['yunit'] == '1'

    assert len(result['series']) == 2

    exp_bins = np.array([-2.33333333333, -2, -1.66666666666]) # for slopes
    exp_slope_dist_values = [0, 3, 0]
    series0 = result['series'][0]
    np.testing.assert_almost_equal(series0['x'], exp_bins)
    np.testing.assert_almost_equal(series0['y'], exp_slope_dist_values)

    # TODO not really testing gauss values yet since number of points is unknown
    # proposal: use a well tested function instead of own formula

