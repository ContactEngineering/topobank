"""
Functions which can be chosen for analysis of topographies.

The first argument is always a PyCo Topography!
"""

import numpy as np

from PyCo.Topography import Topography

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

_analysis_funcs = [] # is used in register_all

def register_all():
    """Registers all analysis functions in the database.

    Use @analysis_function decorator to mark analysis functions
    in the code.

    :returns: number of registered analysis functions
    """
    from .models import AnalysisFunction
    for rf in _analysis_funcs:
        AnalysisFunction.objects.update_or_create(name=rf['name'],
                                                  pyfunc=rf['pyfunc'],
                                                  automatic=rf['automatic'])
    return len(_analysis_funcs)

def analysis_function(card_view_flavor="simple", name=None, automatic=False):
    """Decorator for marking a function as analysis function for a topography.

    :param card_view_flavor: defines how results for this function are displayed, see views.CARD_VIEW_FLAVORS
    :param name: human-readable name, default is to create this from function name
    :param automatic: choose True, if you want to calculate this for every new topography

    See views.py for possible view classes. The should be descendants of the class
    "SimpleCardView".
    """
    def register_decorator(func):
        """
        :param func: function to be registered, first arg must be a Topography
        :return: decorated function
        """

        func.card_view_flavor = card_view_flavor # will be used when choosing the right view on request

        if name is None:
            name_ = func.__name__.replace('_', ' ').title()
        else:
            name_ = name

        # the following data is used in "register_all" to create database objects for the function
        _analysis_funcs.append(dict(
            name = name_,
            pyfunc = func.__name__,
            automatic = automatic
        ))

        return func
    return register_decorator

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

def _reasonable_bins_argument(topography):
    """Returns a reasonable 'bins' argument for np.histogram for given topography's heights.

    :param topography: Line scan or topography from PyCo
    :return: argument for 'bins' argument of np.histogram
    """
    if topography.is_uniform:
        return int(np.sqrt(np.prod(topography.resolution)) + 1.0)
    else:
        return int(np.sqrt(np.prod(len(topography.positions()))) + 1.0) # TODO discuss whether auto or this
        # return 'auto'

def test_function(topography):
    return { 'name': 'Test result for test function called for topography {}.'.format(topography)}
test_function.card_view_flavor = 'simple'

@analysis_function(card_view_flavor='plot', automatic=True)
def height_distribution(topography, bins=None, wfac=5):
    if bins is None:
        bins = _reasonable_bins_argument(topography)

    profile = topography.heights()

    mean_height = np.mean(profile)
    rms_height = topography.rms_height(kind='Sq' if topography.dim == 2 else 'Rq')

    hist, bin_edges = np.histogram(np.ma.compressed(profile), bins=bins, density=True)

    minval = mean_height - wfac * rms_height
    maxval = mean_height + wfac * rms_height
    x_gauss = np.linspace(minval, maxval, 1001)
    y_gauss = np.exp(-(x_gauss - mean_height) ** 2 / (2 * rms_height ** 2)) / (np.sqrt(2 * np.pi) * rms_height)

    try:
        unit = topography.info['unit']
    except:
        unit = None

    return dict(
        name='Height distribution',
        scalars={
            'Mean Height': mean_height, # topography.unit
            'RMS Height': rms_height, # topography.unit
        },
        xlabel='Height',
        ylabel='Probability',
        xunit='' if unit is None else unit,
        yunit='' if unit is None else '{}⁻¹'.format(unit),
        series=[
            dict(name='Height distribution',
                 x=(bin_edges[:-1] + bin_edges[1:]) / 2,
                 y=hist,
                 ),
            dict(name='RMS height',
                 x=x_gauss,
                 y=y_gauss,
                 )
        ]
    )

def _moments_histogram_gaussian(arr, bins, wfac, quantity, label, gaussian=True):
    """Return moments, histogram and gaussian for an array.

    :param arr: array
    :param bins: bins argument for np.histogram
    :param wfac: numeric width factor
    :param quantity: str, what kind of quantity this is (e.g. 'slope)
    :param label: str, how these results should be extra labeled (e.g. 'x direction)
    :param gaussian: bool, if True, add gaussian
    :return: scalars, series

    The result can be used to extend the result dict of the analysis functions, e.g.

    result['scalars'].update(scalars)
    result['series'].extend(series)
    """

    arr = arr.flatten()

    mean = arr.mean()
    rms = np.sqrt((arr**2).mean())
    hist, bin_edges = np.histogram(arr, bins=bins, density=True)

    scalars = {
        f"Mean {quantity.capitalize()} ({label})": mean,
        f"RMS {quantity.capitalize()} ({label})": rms,
    }

    series = [
        dict(name=f'{quantity.capitalize()} distribution ({label})',
             x=(bin_edges[:-1] + bin_edges[1:]) / 2,
             y=hist)]

    if gaussian:
        minval = mean - wfac * rms
        maxval = mean + wfac * rms
        x_gauss = np.linspace(minval, maxval, 1001)
        y_gauss = np.exp(-(x_gauss - mean) ** 2 / (2 * rms ** 2)) / (np.sqrt(2 * np.pi) * rms)

        series.append(
            dict(name=f'RMS {quantity} ({label})',
             x=x_gauss,
             y=y_gauss)
        )

    return scalars, series


@analysis_function(card_view_flavor='plot', automatic=True)
def slope_distribution(topography, bins=None, wfac=5):

    if bins is None:
        bins = _reasonable_bins_argument(topography)

    result = dict(
        name='Slope distribution',
        xlabel='Slope',
        ylabel='Probability',
        xunit='1',
        yunit='1',
        scalars={},
        series=[]
    )
    # .. will be completed below..

    if topography.dim == 2:
        dh_dx, dh_dy = topography.derivative(n=1)
        # dh_dx, dh_dy = np.gradient(topography.heights(), *tuple(topography.pixel_size))
        # not okay for Lars, see GH 83 of PyCo:  https://github.com/pastewka/PyCo/issues/83

        #
        # Results for x direction
        #
        scalars_slope_x, series_slope_x = _moments_histogram_gaussian(dh_dx, bins=bins, wfac=wfac,
                                                                      quantity="slope", label='x direction')
        result['scalars'].update(scalars_slope_x)
        result['series'].extend(series_slope_x)

        #
        # Results for x direction
        #
        scalars_slope_y, series_slope_y = _moments_histogram_gaussian(dh_dy, bins=bins, wfac=wfac,
                                                                      quantity="slope", label='y direction')
        result['scalars'].update(scalars_slope_y)
        result['series'].extend(series_slope_y)

        #
        # Results for absolute gradient
        #
        # TODO how to calculate absolute gradient?
        #
        # absolute_gradients = np.sqrt(dh_dx**2+dh_dy**2)
        # scalars_grad, series_grad = _moments_histogram_gaussian(absolute_gradients, bins=bins, wfac=wfac,
        #                                                         quantity="slope", label='absolute gradient',
        #                                                         gaussian=False)
        # result['scalars'].update(scalars_grad)
        # result['series'].extend(series_grad)


    elif topography.dim == 1:
        dh_dx = topography.derivative(n=1)
        scalars_slope_x, series_slope_x = _moments_histogram_gaussian(dh_dx, bins=bins, wfac=wfac,
                                                                      quantity="slope", label='x direction')
        result['scalars'].update(scalars_slope_x)
        result['series'].extend(series_slope_x)
    else:
        raise ValueError("This analysis function can only handle 1D or 2D topographies.")

    return result

@analysis_function(card_view_flavor='plot', automatic=True)
def curvature_distribution(topography, bins=None, wfac=5):
    if bins is None:
        bins = _reasonable_bins_argument(topography)

    if topography.dim == 2:
        curv_x, curv_y = topography.derivative(n=2)
        curv = curv_x[:, 1:-1] + curv_y[1:-1, :]
    else:
        curv = topography.derivative(n=2)

    mean_curv = np.mean(curv)
    rms_curv = topography.rms_curvature()

    hist, bin_edges = np.histogram(np.ma.compressed(curv), bins=bins,
                                   density=True)

    minval = mean_curv - wfac * rms_curv
    maxval = mean_curv + wfac * rms_curv
    x_gauss = np.linspace(minval, maxval, 1001)
    y_gauss = np.exp(-(x_gauss - mean_curv) ** 2 / (2 * rms_curv ** 2)) / (np.sqrt(2 * np.pi) * rms_curv)

    unit = topography.info['unit']

    return dict(
        name='Curvature distribution',
        scalars={
            'Mean Curvature': mean_curv,
            'RMS Curvature': rms_curv,
        },
        xlabel='Curvature',
        ylabel='Probability',
        xunit='{}⁻¹'.format(unit),
        yunit=unit,
        series=[
            dict(name='Curvature distribution',
                 x=(bin_edges[:-1] + bin_edges[1:]) / 2,
                 y=hist,
                 ),
            dict(name='RMS curvature',
                 x=x_gauss,
                 y=y_gauss,
                 )
        ]
    )

@analysis_function(card_view_flavor='power spectrum', automatic=True)
def power_spectrum(topography, window='hann', tip_radius=None):
    if window == 'None':
        window = None

    q_1D, C_1D = topography.power_spectrum_1D(window=window)
    # Remove NaNs and Infs
    q_1D = q_1D[np.isfinite(C_1D)]
    C_1D = C_1D[np.isfinite(C_1D)]

    unit = topography.info['unit']

    result = dict(
        name='Power-spectral density (PSD)',
        xlabel='Wavevector',
        ylabel='PSD',
        xunit='{}⁻¹'.format(unit),
        yunit='{}³'.format(unit),
        xscale='log',
        yscale='log',
        scalars={
            'Tip radius': tip_radius,
        },
        series=[
            dict(name='1D PSD along x',
                 x=q_1D[1:],
                 y=C_1D[1:],
                 ),
        ]
    )

    if topography.dim == 2:
        #
        # Add two more series with power spectra
        #
        sx, sy = topography.size
        transposed_topography = Topography(topography.heights().T, (sy, sx))
        q_1D_T, C_1D_T = transposed_topography.power_spectrum_1D(window=window)
        q_2D, C_2D = topography.power_spectrum_2D(window=window,
                                                  nbins=len(q_1D) - 1)
        # Remove NaNs and Infs
        q_1D_T = q_1D_T[np.isfinite(C_1D_T)]
        C_1D_T = C_1D_T[np.isfinite(C_1D_T)]
        q_2D = q_2D[np.isfinite(C_2D)]
        C_2D = C_2D[np.isfinite(C_2D)]

        result['series'] = [
            dict(name='q/π × 2D PSD',
                 x=q_2D[1:],
                 y=q_2D[1:] * C_2D[1:] / np.pi,
                 ),
            result['series'][0],
            dict(name='1D PSD along y',
                 x=q_1D_T[1:],
                 y=C_1D_T[1:],
                 )
        ]

    return result

@analysis_function(card_view_flavor='plot', automatic=True)
def autocorrelation(topography):

    if topography.dim == 2:
        sx, sy = topography.size
        transposed_topography = Topography(topography.heights().T, size=(sy,sx), periodic=topography.is_periodic)
        r_T, A_T = transposed_topography.autocorrelation_1D()
        r_2D, A_2D = topography.autocorrelation_2D()

        # Truncate ACF at half the system size
        s = min(sx, sy) / 2
    else:
        s, = topography.size

    r, A = topography.autocorrelation_1D()
    A = A[r < s]
    r = r[r < s]
    # Remove NaNs and Infs
    r = r[np.isfinite(A)]
    A = A[np.isfinite(A)]

    if topography.dim == 2:
        A_T = A_T[r_T < s]
        r_T = r_T[r_T < s]
        A_2D = A_2D[r_2D < s]
        r_2D = r_2D[r_2D < s]

        # Remove NaNs and Infs
        r_T = r_T[np.isfinite(A_T)]
        A_T = A_T[np.isfinite(A_T)]
        r_2D = r_2D[np.isfinite(A_2D)]
        A_2D = A_2D[np.isfinite(A_2D)]

    unit = topography.info['unit']

    #
    # Build series
    #
    series = [dict(name='Along x',
                 x=r,
                 y=A,
                )]

    if topography.dim == 2:
        series=[
            dict(name='Radial average',
                 x=r_2D,
                 y=A_2D,
                 ),
            series[0],
            dict(name='Along y',
                 x=r_T,
                 y=A_T,
                 )
        ]

    return dict(
        name='Height-difference autocorrelation function (ACF)',
        xlabel='Distance',
        ylabel='ACF',
        xunit=unit,
        yunit='{}²'.format(unit),
        xscale='log',
        yscale='log',
        series=series)


@analysis_function(card_view_flavor='plot', automatic=True)
def variable_bandwidth(topography):

    magnifications, bandwidths, rms_heights = topography.variable_bandwidth()

    unit = topography.info['unit']

    return dict(
        name='Variable-bandwidth analysis',
        xlabel='Bandwidth',
        ylabel='RMS Height',
        xunit=unit,
        yunit=unit,
        xscale='log',
        yscale='log',
        series=[
            dict(name='Variable-bandwidth analysis',
                 x=bandwidths,
                 y=rms_heights,
                 ),
        ]
    )
