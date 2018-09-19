"""
Functions which can be chosen for analysis of topographies.

The first argument is always a PyCo Topography!
"""

import numpy as np

from PyCo.Topography import compute_derivative, power_spectrum_1D, power_spectrum_2D, autocorrelation_1D, autocorrelation_2D


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


def float_to_unicode(f, digits=3):
    """
    Convert a floating point number into a human-readable unicode representation.
    Examples are: 1.2×10³, 120.43, 120×10⁻³. Exponents will be multiples of three.

    :param f: Floating-point number for conversion.
    :param digits: Number of significant digits.
    :return: Human-readable unicode string.
    """
    e = int(np.floor(np.log10(f)))
    m = f / 10 ** e

    e3 = (e // 3) * 3
    m *= 10 ** (e - e3)

    if e3 == 0:
        return ('{{:.{}g}}'.format(digits)).format(m)

    else:
        return ('{{:.{}g}}×10{{}}'.format(digits)).format(m, unicode_superscript(str(e3)))


def height_distribution(topography, bins=None, wfac=5):
    if bins is None:
        bins = int(np.sqrt(np.prod(topography.shape)) + 1.0)

    profile = topography.array()

    mean_height = np.mean(profile)
    rms_height = topography.rms_height()

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
        xlabel='Height',
        ylabel='Probability',
        xunit=topography.unit,
        yunit='{}⁻¹'.format(topography.unit),
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
    slope = np.sqrt(2) * np.append(np.ma.compressed(slope_x),
                                   np.ma.compressed(slope_y))

    mean_slope = np.mean(slope)
    rms_slope = topography.rms_slope()

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
    rms_curv = topography.rms_curvature()

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
        xlabel='Curvature',
        ylabel='Probability',
        xunit='{}⁻¹'.format(topography.unit),
        yunit=topography.unit,
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


def power_spectrum(topography, window='hann'):
    if window == 'None':
        window = None

    q_1D, C_1D = power_spectrum_1D(topography, window=window)
    sx, sy = topography.size
    q_1D_T, C_1D_T = power_spectrum_1D(topography.array().T,
                                       size=(sy, sx),
                                       window=window)
    q_2D, C_2D = power_spectrum_2D(topography, window=window,
                                   nbins=len(q_1D) - 1)

    return dict(
        name='Power-spectral density (PSD)',
        xlabel='Wavevector',
        ylabel='PSD',
        xunit='{}⁻¹'.format(topography.unit),
        yunit='{}³'.format(topography.unit),
        xscale='log',
        yscale='log',
        series=[
            dict(name='q/π × 2D PSD',
                 x=q_2D,
                 y=q_2D*C_2D/np.pi,
                 style='o',
                 ),
            dict(name='1D PSD along x',
                 x=q_1D,
                 y=C_1D,
                 style='+',
                 ),
            dict(name='1D PSD along y',
                 x=q_1D_T,
                 y=C_1D_T,
                 style='y',
                 )
        ]
    )


def autocorrelation(topography):
    r, A = autocorrelation_1D(topography)
    sx, sy = topography.size
    r_T, A_T = autocorrelation_1D(topography.array().T, size=(sy, sx))
    r_2D, A_2D = autocorrelation_2D(topography)

    # Truncate ACF at half the system size
    s = min(sx, sy) / 2
    A = A[r < s]
    r = r[r < s]
    A_T = A_T[r_T < s]
    r_T = r_T[r_T < s]
    A_2D = A_2D[r_2D < s]
    r_2D = r_2D[r_2D < s]

    return dict(
        name='Height-difference autocorrelation function (ACF)',
        xlabel='Distance',
        ylabel='ACF',
        xunit=topography.unit,
        yunit='{}²'.format(topography.unit),
        xscale='log',
        yscale='log',
        series=[
            dict(name='Radial average',
                 x=r_2D,
                 y=A_2D,
                 style='o',
                 ),
            dict(name='Along x',
                 x=r,
                 y=A,
                 style='+',
                 ),
            dict(name='Along y',
                 x=r_T,
                 y=A_T,
                 style='y',
                 )
        ]
    )
