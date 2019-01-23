from PyCo.Topography import NonuniformNumpyTopography
from PyCo.Topography.TopographyPipeline import DetrendedTopography, ScaledTopography
import numpy as np
import pytest
import math

from topobank.analysis.functions import height_distribution

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

