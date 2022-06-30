"""Special test for reentrant surfaces"""

import pytest
import io

from SurfaceTopography.IO import read_topography

from ..functions import ReentrantTopographyException
from ...statistical_analysis.functions import slope_distribution, curvature_distribution, power_spectrum, \
    autocorrelation, scale_dependent_slope, scale_dependent_curvature
from .test_functions import FakeTopographyModel


@pytest.fixture
def reentrant_line_scan():
    """Return an reentrant line scan."""
    data = """
    0 1
    1 1
    2 1
    2 2
    3 2
    4 2
    """
    in_mem_file = io.StringIO(data)
    return read_topography(in_mem_file)


@pytest.mark.parametrize('analysis_func', [power_spectrum, slope_distribution, curvature_distribution, autocorrelation,
                                           scale_dependent_slope, scale_dependent_curvature])
def test_power_spectrum(reentrant_line_scan, analysis_func):
    topo = FakeTopographyModel(reentrant_line_scan)
    with pytest.raises(ReentrantTopographyException) as exc:
        analysis_func(topo)
