"""
Functions which can be chosen for analysis of topographies.

The first argument is always a PyCo Topography!
"""

import numpy as np
import tempfile

# These imports are needed for storage
from django.core.files.storage import default_storage
from django.core.files import File
import xarray as xr

from PyCo.Topography import Topography

from PyCo.SolidMechanics import PeriodicFFTElasticHalfSpace, FreeFFTElasticHalfSpace
from PyCo.ContactMechanics import HardWall
from PyCo.System.Factory import make_system
from PyCo.Topography import PlasticTopography


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

        # TODO: Can a default argument be automated without writing it?
        # Add progress_recorder argument with default value, if not defined:
        # sig = signature(func)
        #if 'progress_recorder' not in sig.parameters:
        #    func = lambda *args, **kw: func(*args, progress_recorder=ConsoleProgressRecorder(), **kw)
        #    # the console progress recorder will work in tests and when calling the function
        #    # outside of an celery context
        #    #
        #    # When used in a celery context, this argument will be overwritten with
        #    # another recorder updated by a celery task

        func.card_view_flavor = card_view_flavor  # will be used when choosing the right view on request

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

#
# Use this during development if you need a long running task with failures
#
# @analysis_function(card_view_flavor='simple', automatic=True)
# def long_running_task(topography, progress_recorder=None):
#     import time, random
#     n = 10 + random.randint(1,10)
#     F = 30
#     for i in range(n):
#         time.sleep(0.5)
#         if random.randint(1, F) == 1:
#             raise ValueError("This error is intended and happens with probability 1/{}.".format(F))
#         progress_recorder.set_progress(i+1, n)
#     return dict(message="done", size=topography.size, n=n)

@analysis_function(card_view_flavor='plot', automatic=True)
def height_distribution(topography, bins=None, wfac=5, progress_recorder=None, storage_prefix=None):
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
def slope_distribution(topography, bins=None, wfac=5, progress_recorder=None, storage_prefix=None):

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
def curvature_distribution(topography, bins=None, wfac=5, progress_recorder=None, storage_prefix=None):
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

@analysis_function(card_view_flavor='plot', automatic=True)
def power_spectrum(topography, window='hann', tip_radius=None, progress_recorder=None, storage_prefix=None):
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
def autocorrelation(topography, progress_recorder=None, storage_prefix=None):

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
def variable_bandwidth(topography, progress_recorder=None, storage_prefix=None):

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

def _next_contact_step(system, history=None, pentol=None, maxiter=None):
    """
    Run a full contact calculation. Try to guess displacement such that areas
    are equally spaced on a log scale.

    Parameters
    ----------
    system : PyCo.System.SystemBase object
        The contact mechanical system.
    history : tuple
        History returned by past calls to next_step

    Returns
    -------
    displacements : numpy.ndarray
        Current surface displacement field.
    forces : numpy.ndarray
        Current surface pressure field.
    displacement : float
        Current displacement of the rigid surface
    load : float
        Current load.
    area : float
        Current fractional contact area.
    history : tuple
        History of contact calculations.
    """

    topography = system.surface
    substrate = system.substrate

    # Get the profile as a numpy array
    profile = topography.heights()

    # Find max, min and mean heights
    top = np.max(profile)
    middle = np.mean(profile)
    bot = np.min(profile)

    if history is None:
        step = 0
    else:
        disp, gap, load, area, converged = history
        step = len(disp)

    if step == 0:
        disp = []
        gap = []
        load = []
        area = []
        converged = np.array([], dtype=bool)

        disp0 = -middle
    elif step == 1:
        disp0 = -top + 0.01 * (top - middle)
    else:
        ref_area = np.log10(np.array(area + 1 / np.prod(topography.resolution)))
        darea = np.append(ref_area[1:] - ref_area[:-1], -ref_area[-1])
        i = np.argmax(darea)
        if i == step - 1:
            disp0 = bot + 2 * (disp[-1] - bot)
        else:
            disp0 = (disp[i] + disp[i + 1]) / 2

    # TODO: This is a mess. We should give variables more explicit names. Also double check that this works for both
    # periodic and non-periodic calculations.
    opt = system.minimize_proxy(offset=disp0, pentol=pentol, maxiter=maxiter)
    force_xy = opt.jac
    displacement_xy = opt.x[:force_xy.shape[0], :force_xy.shape[1]]
    disp = np.append(disp, [disp0])
    gap = np.append(gap, [np.mean(displacement_xy) - middle - disp0])
    current_load = force_xy.sum() / np.prod(topography.size)
    load = np.append(load, [current_load])
    current_area = (force_xy > 0).sum() / np.prod(topography.resolution)
    area = np.append(area, [current_area])
    converged = np.append(converged, np.array([opt.success], dtype=bool))

    area_per_pt = substrate.area_per_pt
    pressure_xy = force_xy / area_per_pt
    gap_xy = displacement_xy - topography.heights() - opt.offset
    gap_xy[gap_xy < 0.0] = 0.0




    return displacement_xy, gap_xy, pressure_xy, disp0, current_load, current_area, (disp, gap, load, area, converged)

@analysis_function(card_view_flavor='contact mechanics', automatic=True)
def contact_mechanics(topography, substrate_str="periodic", hardness=None, nsteps=10,
                      progress_recorder=None, storage_prefix=None):

    #
    # Some constants
    #
    maxiter = 100
    min_pentol = 1e-12  # lower bound for the penetration tolerance

    if (hardness is not None) and (hardness > 0):
        topography = PlasticTopography(topography, hardness)

    half_space_factory = dict(periodic=PeriodicFFTElasticHalfSpace,
                              nonperiodic=FreeFFTElasticHalfSpace)

    substrate = half_space_factory[substrate_str](topography.resolution, 1.0, topography.size)

    interaction = HardWall()
    system = make_system(substrate, interaction, topography)

    # Heuristics for the possible tolerance on penetration.
    # This is necessary because numbers can vary greatly
    # depending on the system of units.
    pentol = topography.rms_height() / (10 * np.mean(topography.resolution))
    pentol = max(pentol, min_pentol)

    data_paths = [] # collect in _next_contact_step?

    history = None
    for i in range(nsteps):
        displacement_xy, gap_xy, pressure_xy, disp0, current_load, current_area, history = \
            _next_contact_step(system, history=history, pentol=pentol, maxiter=maxiter)
        #
        # Save displacement_xy, gap_xy and pressure_xy to storage, will be retrieved later for visualization
        #
        pressure_xy = xr.DataArray(pressure_xy, dims=('x', 'y')) # maybe define coordinates
        gap_xy = xr.DataArray(gap_xy, dims=('x', 'y'))
        displacement_xy = xr.DataArray(displacement_xy, dims=('x', 'y'))

        dataset = xr.Dataset({'pressure': pressure_xy,
                              'gap': gap_xy,
                              'displacement': displacement_xy}) # one dataset per analysis step: smallest unit to retrieve
        dataset.attrs['load'] = current_load
        dataset.attrs['area'] = current_area

        with tempfile.NamedTemporaryFile(prefix='analysis-') as tmpfile:

            dataset.to_netcdf(tmpfile.name, format='NETCDF3_CLASSIC')

            storage_path = storage_prefix+"result-step-{}.nc".format(i)
            tmpfile.seek(0)
            storage_path = default_storage.save(storage_path, File(tmpfile))
            data_paths.append(storage_path)

        progress_recorder.set_progress(i + 1, nsteps)

    disp, gap, load, area, converged = history

    load = np.array(load)
    area = np.array(area)
    disp = np.array(disp)
    gap = np.array(gap)
    converged = np.array(converged)

    data_paths = np.array(data_paths, dtype='str')
    sort_order = np.argsort(load)

    return dict(
        name='Contact mechanics',
        area_per_pt=substrate.area_per_pt,
        maxiter=maxiter,
        min_pentol=min_pentol,
        loads=load[sort_order],
        areas=area[sort_order],
        disps=disp[sort_order],
        gaps=gap[sort_order],
        converged=converged[sort_order],
        data_paths=data_paths[sort_order],
    )

