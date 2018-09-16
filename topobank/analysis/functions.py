"""
Functions which can be chosen for analysis of topographies.

The first argument is always a PyCo Topography!
"""

import numpy as np

from PyCo.Tools import compute_derivative


def height_distribution(topography, bins=None, wfac=5):
    if bins is None:
        bins = int(np.sqrt(np.prod(topography.shape)) + 1.0)

    profile = topography.profile()

    mean_height = np.mean(profile)
    rms_height = topography.compute_rms_height()

    hist, bin_edges = np.histogram(np.ma.compressed(profile), bins=bins, density=True)

    minval = mean_height - wfac * rms_height
    maxval = mean_height + wfac * rms_height
    x_gauss = np.linspace(minval, maxval, 1001)
    y_gauss = np.exp(-(x_gauss - mean_height) ** 2 / (2 * rms_height ** 2)) / (np.sqrt(2 * np.pi) * rms_height)

    return dict(
        name='Height distribution',
        scalars=dict(
            mean_height=mean_height,
            rms_height=rms_height,
        ),
        xlabel='Height ({})'.format(topography.unit),
        ylabel='Probability ({}⁻¹)'.format(topography.unit),
        series=[
            dict(name='Height distribution',
                 x=(bin_edges[:-1] + bin_edges[1:]) / 2,
                 y=hist,
                 style='k-',
                 ),
            dict(name='Gaussian',
                 x=x_gauss,
                 y=y_gauss,
                 style='r-',
                 )
        ]
    )


def slope_distribution(topography, bins=None, wfac=5):
    if bins is None:
        bins = int(np.sqrt(np.prod(topography.shape)) + 1.0)

    slope_x, slope_y = compute_derivative(topography)
    slope = np.sqrt(2)*np.append(np.ma.compressed(slope_x),
                                 np.ma.compressed(slope_y))

    mean_slope = np.mean(slope)
    rms_slope = topography.compute_rms_slope()

    hist, bin_edges = np.histogram(slope, bins=bins, density=True)

    minval = mean_slope - wfac * rms_slope
    maxval = mean_slope + wfac * rms_slope
    x_gauss = np.linspace(minval, maxval, 1001)
    y_gauss = np.exp(-(x_gauss - mean_slope) ** 2 / (2 * rms_slope ** 2)) / (np.sqrt(2 * np.pi) * rms_slope)

    return dict(
        name='Slope distribution',
        scalars=dict(
            mean_slope=mean_slope,
            rms_slope=rms_slope,
        ),
        xlabel='Slope',
        ylabel='Probability',
        series=[
            dict(name='Slope distribution',
                 x=(bin_edges[:-1] + bin_edges[1:]) / 2,
                 y=hist,
                 style='k-',
                 ),
            dict(name='Gaussian',
                 x=x_gauss,
                 y=y_gauss,
                 style='r-',
                 )
        ]
    )
