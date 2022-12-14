import numpy as np
import math
import pytest
from numpy.testing import assert_allclose



import topobank.analysis.functions
from topobank.analysis.functions import (
    IncompatibleTopographyException)


from topobank.manager.tests.utils import SurfaceFactory, Topography1DFactory

#EXPECTED_KEYS_FOR_DIST_ANALYSIS = sorted(['name', 'scalars', 'xlabel', 'ylabel', 'xunit', 'yunit', 'series'])
#EXPECTED_KEYS_FOR_PLOT_CARD_ANALYSIS = sorted(['alerts', 'name',
#                                               'xlabel', 'ylabel', 'xunit', 'yunit',
#                                               'xscale', 'yscale', 'series'])

###############################################################################
# Helpers for doing tests
###############################################################################



###############################################################################
# Testing analysis functions for surfaces
###############################################################################

