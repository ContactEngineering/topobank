"""
Functions which can be chosen for analysis of topographies.

The first argument is always a PyCo Topography!
"""

import numpy as np

from PyCo.Topography import rms_height
from PyCo.Topography.common import _get_size, compute_derivative
from PyCo.Topography.PowerSpectrum import power_spectrum_1D, power_spectrum_2D
from PyCo.Topography.Autocorrelation import autocorrelation_1D, autocorrelation_2D
from PyCo.Topography.VariableBandwidth import checkerboard_tilt_correction

# TODO: _unicode_map and super and subscript functions should be moved to some support module.

_unicode_map = {
    # superscript subscript
    '0': ('\u2070', '\u2080'),
    '1': ('\u00B9', '\u2081'),
    '2': ('\u00B2', '\u2082'),
    '3': ('\u00B3', '\u2083'),
    '4': ('\u2074', '\u2084'),
    '5': ('\u2075', '\u2085'),
    '6': ('\u2076', '\u2086'),
    '7': ('\u2077', '\u2087'),
    '8': ('\u2078', '\u2088'),
    '9': ('\u2079', '\u2089'),
    'a': ('\u1d43', '\u2090'),
    'b': ('\u1d47', '?'),
    'c': ('\u1d9c', '?'),
    'd': ('\u1d48', '?'),
    'e': ('\u1d49', '\u2091'),
    'f': ('\u1da0', '?'),
    'g': ('\u1d4d', '?'),
    'h': ('\u02b0', '\u2095'),
    'i': ('\u2071', '\u1d62'),
    'j': ('\u02b2', '\u2c7c'),
    'k': ('\u1d4f', '\u2096'),
    'l': ('\u02e1', '\u2097'),
    'm': ('\u1d50', '\u2098'),
    'n': ('\u207f', '\u2099'),
    'o': ('\u1d52', '\u2092'),
    'p': ('\u1d56', '\u209a'),
    'q': ('?', '?'),
    'r': ('\u02b3', '\u1d63'),
    's': ('\u02e2', '\u209b'),
    't': ('\u1d57', '\u209c'),
    'u': ('\u1d58', '\u1d64'),
    'v': ('\u1d5b', '\u1d65'),
    'w': ('\u02b7', '?'),
    'x': ('\u02e3', '\u2093'),
    'y': ('\u02b8', '?'),
    'z': ('?', '?'),
    'A': ('\u1d2c', '?'),
    'B': ('\u1d2e', '?'),
    'C': ('?', '?'),
    'D': ('\u1d30', '?'),
    'E': ('\u1d31', '?'),
    'F': ('?', '?'),
    'G': ('\u1d33', '?'),
    'H': ('\u1d34', '?'),
    'I': ('\u1d35', '?'),
    'J': ('\u1d36', '?'),
    'K': ('\u1d37', '?'),
    'L': ('\u1d38', '?'),
    'M': ('\u1d39', '?'),
    'N': ('\u1d3a', '?'),
    'O': ('\u1d3c', '?'),
    'P': ('\u1d3e', '?'),
    'Q': ('?', '?'),
    'R': ('\u1d3f', '?'),
    'S': ('?', '?'),
    'T': ('\u1d40', '?'),
    'U': ('\u1d41', '?'),
    'V': ('\u2c7d', '?'),
    'W': ('\u1d42', '?'),
    'X': ('?', '?'),
    'Y': ('?', '?'),
    'Z': ('?', '?'),
    '+': ('\u207A', '\u208A'),
    '-': ('\u207B', '\u208B'),
    '=': ('\u207C', '\u208C'),
    '(': ('\u207D', '\u208D'),
    ')': ('\u207E', '\u208E'),
    ':alpha': ('\u1d45', '?'),
    ':beta': ('\u1d5d', '\u1d66'),
    ':gamma': ('\u1d5e', '\u1d67'),
    ':delta': ('\u1d5f', '?'),
    ':epsilon': ('\u1d4b', '?'),
    ':theta': ('\u1dbf', '?'),
    ':iota': ('\u1da5', '?'),
    ':pho': ('?', '\u1d68'),
    ':phi': ('\u1db2', '?'),
    ':psi': ('\u1d60', '\u1d69'),
    ':chi': ('\u1d61', '\u1d6a'),
    ':coffee': ('\u2615', '\u2615')
}


def unicode_superscript(s):
    """
    Convert a string into the unicode superscript equivalent.

    :param s: Input string
    :return: String with superscript numerals
    """
    return ''.join(_unicode_map[c][0] if c in _unicode_map else c for c in s)


def unicode_subscript(s):
    """
    Convert numerals inside a string into the unicode subscript equivalent.

    :param s: Input string
    :return: String with superscript numerals
    """
    return ''.join(_unicode_map[c][1] if c in _unicode_map else c for c in s)


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

    # Remove NaNs and Infs
    q_1D = q_1D[np.isfinite(C_1D)]
    C_1D = C_1D[np.isfinite(C_1D)]
    q_1D_T = q_1D_T[np.isfinite(C_1D_T)]
    C_1D_T = C_1D_T[np.isfinite(C_1D_T)]
    q_2D = q_2D[np.isfinite(C_2D)]
    C_2D = C_2D[np.isfinite(C_2D)]

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
                 x=q_2D[1:],
                 y=q_2D[1:] * C_2D[1:] / np.pi,
                 style='o-',
                 ),
            dict(name='1D PSD along x',
                 x=q_1D[1:],
                 y=C_1D[1:],
                 style='+-',
                 ),
            dict(name='1D PSD along y',
                 x=q_1D_T[1:],
                 y=C_1D_T[1:],
                 style='y-',
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

    # Remove NaNs and Infs
    r = r[np.isfinite(A)]
    A = A[np.isfinite(A)]
    r_T = r_T[np.isfinite(A_T)]
    A_T = A_T[np.isfinite(A_T)]
    r_2D = r_2D[np.isfinite(A_2D)]
    A_2D = A_2D[np.isfinite(A_2D)]

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
                 style='o-',
                 ),
            dict(name='Along x',
                 x=r,
                 y=A,
                 style='+-',
                 ),
            dict(name='Along y',
                 x=r_T,
                 y=A_T,
                 style='y-',
                 )
        ]
    )


def variable_bandwidth(topography):
    size = _get_size(topography)
    scale_factor = 1
    no_exception = True
    bandwidths = []
    rms_heights = []
    while no_exception and scale_factor < 128:
        no_exception = False
        try:
            s = checkerboard_tilt_correction(topography, sd=(scale_factor, )*topography.dim)
            bandwidths += [np.mean(size)/scale_factor]
            rms_heights += [rms_height(s)]
            no_exception = True
        except np.linalg.LinAlgError:
            pass
        scale_factor *= 2

    return dict(
        name='Variable-bandwidth analysis',
        xlabel='Bandwidth',
        ylabel='RMS Height',
        xunit=topography.unit,
        yunit=topography.unit,
        xscale='log',
        yscale='log',
        series=[
            dict(name='Variable-bandwidth analysis',
                 x=bandwidths,
                 y=rms_heights,
                 style='o-',
                 ),
        ]
    )

