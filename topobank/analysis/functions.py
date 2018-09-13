"""
Functions which can be chosen for analysis of topographies.

The first argument is always a PyCo Topography!
"""

import numpy as np

def height_distribution(surface, bins=None):

    if bins is None:
        bins = int(np.sqrt(np.prod(surface.shape))+1.0)

    profile = surface.profile()

    mean_height = np.mean(profile)
    rms_height = surface.compute_rms_height()

    hist, bin_edges = np.histogram(np.ma.compressed(profile), bins=bins, normed=True)

    return {
        'mean_height': mean_height,
        'rms_height': rms_height,
        'hist': hist,
        'bin_edges': bin_edges,
    }


