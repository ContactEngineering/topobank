"""
Functions which can be chosen for analysis of topographies.

The first argument is always a PyCo Topography!
"""

import numpy as np

from PyCo.Tools import compute_derivative


def unicode_superscript(s):
    """
    Convert numerals inside a string into the unicode superscript equivalent.

    :param s: Input string
    :return: String with superscript numerals
    """
    superscript_dict = {
        '0': '⁰',
        '1': '¹',
        '2': '²',
        '3': '³',
        '4': '⁴',
        '5': '⁵',
        '6': '⁶',
        '7': '⁷',
        '8': '⁸',
        '9': '⁹',
        '+': '⁺',
        '-': '⁻',
        '.': '⋅',
    }
    return ''.join(superscript_dict[c] if c in superscript_dict else c for c in s)


def float_to_unicode(f, dig=3):
    """
    Convert a floating point number into a human-readable unicode representation.
    Examples are: 1.2×10³, 120.43, 120×10⁻³. Exponents will be multiples of three.

    :param f: Floating-point number for conversion.
    :param dig: Number of significant digits.
    :return: Human-readable unicode string.
    """
    e = int(np.floor(np.log10(f)))
    m = f / 10 ** e

    e3 = (e // 3) * 3
    m *= 10 ** (e - e3)

    if e3 == 0:
        return ('{{:.{}g}}'.format(dig)).format(m)

    else:
        return ('{{:.{}g}}×10{{}}'.format(dig)).format(m, unicode_superscript(str(e3)))


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
            dict(name='RMS height: {} {}'.format(float_to_unicode(rms_height), topography.unit),
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
            dict(name='RMS slope: {}'.format(float_to_unicode(rms_slope)),
                 x=x_gauss,
                 y=y_gauss,
                 style='r-',
                 )
        ]
    )


def curvature_distribution(topography, bins=None, wfac=5):
    if bins is None:
        bins = int(np.sqrt(np.prod(topography.shape)) + 1.0)

    curv_x, curv_y = compute_derivative(topography, n=2)
    curv = curv_x[:, 1:-1] + curv_y[1:-1, :]

    mean_curv = np.mean(curv)
    rms_curv = topography.compute_rms_curvature()

    hist, bin_edges = np.histogram(np.ma.compressed(curv), bins=bins,
                                   density=True)

    minval = mean_curv - wfac * rms_curv
    maxval = mean_curv + wfac * rms_curv
    x_gauss = np.linspace(minval, maxval, 1001)
    y_gauss = np.exp(-(x_gauss - mean_curv) ** 2 / (2 * rms_curv ** 2)) / (np.sqrt(2 * np.pi) * rms_curv)

    return dict(
        name='Curvature distribution',
        scalars=dict(
            mean_curvature=mean_curv,
            rms_curvature=rms_curv,
        ),
        xlabel='Curvature ({}⁻¹)'.format(topography.unit),
        ylabel='Probability ({})'.format(topography.unit),
        series=[
            dict(name='Curvature distribution',
                 x=(bin_edges[:-1] + bin_edges[1:]) / 2,
                 y=hist,
                 style='k-',
                 ),
            dict(name='RMS curvature: {} {}⁻¹'.format(float_to_unicode(rms_curv), topography.unit),
                 x=x_gauss,
                 y=y_gauss,
                 style='r-',
                 )
        ]
    )
