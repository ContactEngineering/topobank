"""
Implementations of analysis functions for topographies and surfaces.

The first argument is either a Topography or Surface instance (model).
"""
import collections

from django.core.files.storage import default_storage
from django.core.files import File
from django.conf import settings

import xarray as xr
import numpy as np
import tempfile
from pint import UnitRegistry, UndefinedUnitError
from scipy.interpolate import interp1d
import scipy.stats

from SurfaceTopography import PlasticTopography
from SurfaceTopography.Container.common import bandwidth, suggest_length_unit
from SurfaceTopography.Container.Averaging import log_average
from SurfaceTopography.Container.ScaleDependentStatistics import scale_dependent_statistical_property
from ContactMechanics import PeriodicFFTElasticHalfSpace, FreeFFTElasticHalfSpace, make_system

import topobank.manager.models  # will be used to evaluate model classes
from .registry import AnalysisFunctionRegistry

GAUSSIAN_FIT_SERIES_NAME = 'Gaussian fit'


def register_implementation(card_view_flavor="simple", name=None):
    """Decorator for marking a function as implementation for an analysis function.

    :param card_view_flavor: defines how results for this function are displayed, see views.CARD_VIEW_FLAVORS
    :param name: human-readable name, default is to create this from function name

    Only card_view_flavor can be used which are defined in the
    AnalysisFunction model. Additionally See views.py for possible view classes.
    They should be descendants of the class "SimpleCardView".
    """

    def register_decorator(func):
        """
        :param func: function to be registered, first arg must be a "topography" or "surface"
        :return: decorated function

        Depending on the name of the first argument, you get either a Topography
        or a Surface instance.
        """
        registry = AnalysisFunctionRegistry()  # singleton
        registry.add_implementation(name, card_view_flavor, func)
        return func

    return register_decorator


class ContainerProxy(collections.Iterator):
    """
    Proxy class that emulates a SurfaceTopography `Container` and can be used
    to iterate over native SurfaceTopography objects.
    """

    def __init__(self, obj):
        self._obj = obj
        self._iter = iter(obj)

    def __len__(self):
        return len(self._obj)

    def __iter__(self):
        return ContainerProxy(self._obj)

    def __next__(self):
        return next(self._iter).topography()


def _reasonable_bins_argument(topography):
    """Returns a reasonable 'bins' argument for np.histogram for given topography's heights.

    :param topography: Line scan or topography from SurfaceTopography module
    :return: argument for 'bins' argument of np.histogram
    """
    if topography.is_uniform:
        return int(np.sqrt(np.prod(topography.nb_grid_pts)) + 1.0)
    else:
        return int(np.sqrt(np.prod(len(topography.positions()))) + 1.0)  # TODO discuss whether auto or this
        # return 'auto'


def _logspace_full_decades(minval, maxval, points_per_decade=5):
    log_minval = int(np.floor(np.log10(minval)))
    log_maxval = int(np.ceil(np.log10(maxval)))
    s = np.logspace(log_minval, log_maxval, points_per_decade * (log_maxval - log_minval) + 1)
    return s[np.logical_and(s >= minval, s <= maxval)]


class IncompatibleTopographyException(Exception):
    """Raise this exception in case a function cannot handle a topography.

    By handling this special exception, the UI can show the incompatibility
    as note to the user, not as failure. It is an excepted failure.
    """
    pass


class ReentrantTopographyException(IncompatibleTopographyException):
    """Raise this exception if a function cannot handle a topography because it is reentrant.

    By handling this special exception, the UI can show the incompatibility
    as note to the user, not as failure. It is an excepted failure.
    """
    pass


#
# Use this during development if you need a long running task with failures
#
# @analysis_function(card_view_flavor='simple')
# def long_running_task(topography, progress_recorder=None, storage_prefix=None):
#     topography = topography.topography()
#     import time, random
#     n = 10 + random.randint(1,10)
#     F = 30
#     for i in range(n):
#         time.sleep(0.5)
#         if random.randint(1, F) == 1:
#             raise ValueError("This error is intended and happens with probability 1/{}.".format(F))
#         progress_recorder.set_progress(i+1, n)
#     return dict(message="done", physical_sizes=topography.physical_sizes, n=n)


@register_implementation(name="Height distribution", card_view_flavor='plot')
def height_distribution(topography, bins=None, wfac=5, progress_recorder=None, storage_prefix=None):
    # Get low level topography from SurfaceTopography model
    topography = topography.topography()

    if bins is None:
        bins = _reasonable_bins_argument(topography)

    profile = topography.heights()

    mean_height = np.mean(profile)
    rms_height = topography.rms_height_from_area() if topography.dim == 2 else topography.rms_height_from_profile()

    hist, bin_edges = np.histogram(np.ma.compressed(profile), bins=bins, density=True)

    minval = mean_height - wfac * rms_height
    maxval = mean_height + wfac * rms_height
    x_gauss = np.linspace(minval, maxval, 1001)
    y_gauss = np.exp(-(x_gauss - mean_height) ** 2 / (2 * rms_height ** 2)) / (np.sqrt(2 * np.pi) * rms_height)

    try:
        unit = topography.unit
    except:
        unit = None

    return dict(
        name='Height distribution',
        scalars={
            'Mean Height': dict(value=mean_height, unit=unit),
            'RMS Height': dict(value=rms_height, unit=unit),
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
            dict(name=GAUSSIAN_FIT_SERIES_NAME,
                 x=x_gauss,
                 y=y_gauss,
                 )
        ]
    )


def _reasonable_histogram_range(arr):
    """Return 'range' argument for np.histogram

    Fixes problem with too small default ranges
    which is roughly arr.max()-arr.min() < 1e-08.
    We take 5*e-8 as threshold in order to be safe.

    Parameters
    ----------
    arr: array
        array to calculate histogram for

    Returns
    -------
    (float, float)
    The lower and upper range of the bins.

    """
    arr_min = arr.min()
    arr_max = arr.max()

    if arr_max - arr_min < 5e-8:
        hist_range = (arr_min - 1e-3, arr_max + 1e-3)
    else:
        hist_range = (arr_min, arr_max)
    return hist_range


def _moments_histogram_gaussian(arr, bins, topography, wfac, quantity, label, unit, gaussian=True):
    """Return moments, histogram and gaussian for an array.
    :param arr: array, array to calculate moments and histogram for
    :param bins: bins argument for np.histogram
    :param topography: SurfaceTopography topography instance, used for histogram ranges
    :param wfac: numeric width factor
    :param quantity: str, what kind of quantity this is (e.g. 'slope')
    :param label: str, how these results should be extra labeled (e.g. 'x direction')
    :param unit: str, unit of the quantity (e.g. '1/nm')
    :param gaussian: bool, if True, add gaussian
    :return: scalars, series

    The result can be used to extend the result dict of the analysis functions, e.g.

    result['scalars'].update(scalars)
    result['series'].extend(series)
    """

    arr = arr.flatten()

    mean = arr.mean()
    rms = np.sqrt((arr ** 2).mean())

    try:
        hist, bin_edges = np.histogram(arr, bins=bins, density=True,
                                       range=_reasonable_histogram_range(arr))
    except (ValueError, RuntimeError) as exc:
        # Workaround for GH #683 in order to recognize reentrant measurements.
        # Replace with catching of specific exception when
        # https://github.com/ContactEngineering/SurfaceTopography/issues/108 is implemented.
        if (len(exc.args) > 0) and \
           ((exc.args[0] == 'supplied range of [0.0, inf] is not finite') or ('is reentrant' in exc.args[0])):
            raise ReentrantTopographyException("Cannot calculate curvature distribution for reentrant measurements.")
        raise

    scalars = {
        f"Mean {quantity.capitalize()} ({label})": dict(value=mean, unit=unit),
        f"RMS {quantity.capitalize()} ({label})": dict(value=rms, unit=unit),
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
            dict(name=GAUSSIAN_FIT_SERIES_NAME + f' ({label})',
                 x=x_gauss,
                 y=y_gauss)
        )

    return scalars, series


@register_implementation(name="Slope distribution", card_view_flavor='plot')
def slope_distribution(topography, bins=None, wfac=5, progress_recorder=None, storage_prefix=None):
    """Calculates slope distribution for given topography."""
    # Get low level topography from SurfaceTopography model
    topography = topography.topography()

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

        #
        # Results for x direction
        #
        scalars_slope_x, series_slope_x = _moments_histogram_gaussian(dh_dx, bins=bins,
                                                                      topography=topography,
                                                                      wfac=wfac,
                                                                      quantity="slope", unit='1',
                                                                      label='x direction')
        result['scalars'].update(scalars_slope_x)
        result['series'].extend(series_slope_x)

        #
        # Results for y direction
        #
        scalars_slope_y, series_slope_y = _moments_histogram_gaussian(dh_dy, bins=bins,
                                                                      topography=topography,
                                                                      wfac=wfac,
                                                                      quantity="slope", unit='1',
                                                                      label='y direction')
        result['scalars'].update(scalars_slope_y)
        result['series'].extend(series_slope_y)

        #
        # Results for absolute gradient
        #
        # Not sure so far, how to calculate absolute gradient..
        #
        # absolute_gradients = np.sqrt(dh_dx**2+dh_dy**2)
        # scalars_grad, series_grad = _moments_histogram_gaussian(absolute_gradients, bins=bins, wfac=wfac,
        #                                                         quantity="slope", unit="?",
        #                                                         label='absolute gradient',
        #                                                         gaussian=False)
        # result['scalars'].update(scalars_grad)
        # result['series'].extend(series_grad)

    elif topography.dim == 1:
        dh_dx = topography.derivative(n=1)
        scalars_slope_x, series_slope_x = _moments_histogram_gaussian(dh_dx, bins=bins,
                                                                      topography=topography,
                                                                      wfac=wfac,
                                                                      quantity="slope", unit='1',
                                                                      label='x direction')
        result['scalars'].update(scalars_slope_x)
        result['series'].extend(series_slope_x)
    else:
        raise ValueError("This analysis function can only handle 1D or 2D topographies.")

    return result


@register_implementation(name="Curvature distribution", card_view_flavor='plot')
def curvature_distribution(topography, bins=None, wfac=5, progress_recorder=None, storage_prefix=None):
    # Get low level topography from SurfaceTopography model
    topography = topography.topography()

    if bins is None:
        bins = _reasonable_bins_argument(topography)

    #
    # Calculate the Laplacian
    #
    if topography.dim == 2:
        curv_x, curv_y = topography.derivative(n=2)
        curv = curv_x + curv_y
    else:
        curv = topography.derivative(n=2)

    mean_curv = np.mean(curv)
    rms_curv = topography.rms_curvature_from_area() if topography.dim == 2 else topography.rms_curvature_from_profile()
    # rms_curv = topography.rms_curvature()

    hist_arr = np.ma.compressed(curv)

    try:
        hist, bin_edges = np.histogram(hist_arr, bins=bins,
                                       range=_reasonable_histogram_range(hist_arr),
                                       density=True)
    except (ValueError, RuntimeError) as exc:
        # Workaround for GH #683 in order to recognize reentrant measurements.
        # Replace with catching of specific exception when
        # https://github.com/ContactEngineering/SurfaceTopography/issues/108 is implemented.
        if (len(exc.args) > 0) and \
           ((exc.args[0] == 'supplied range of [-inf, inf] is not finite') or ('is reentrant' in exc.args[0])):
            raise ReentrantTopographyException("Cannot calculate curvature distribution for reentrant measurements.")
        raise

    minval = mean_curv - wfac * rms_curv
    maxval = mean_curv + wfac * rms_curv
    x_gauss = np.linspace(minval, maxval, 1001)
    y_gauss = np.exp(-(x_gauss - mean_curv) ** 2 / (2 * rms_curv ** 2)) / (np.sqrt(2 * np.pi) * rms_curv)

    unit = topography.unit
    inverse_unit = '{}⁻¹'.format(unit)

    return dict(
        name='Curvature distribution',
        scalars={
            'Mean Curvature': dict(value=mean_curv, unit=inverse_unit),
            'RMS Curvature': dict(value=rms_curv, unit=inverse_unit),
        },
        xlabel='Curvature',
        ylabel='Probability',
        xunit=inverse_unit,
        yunit=unit,
        series=[
            dict(name='Curvature distribution',
                 x=(bin_edges[:-1] + bin_edges[1:]) / 2,
                 y=hist,
                 ),
            dict(name=GAUSSIAN_FIT_SERIES_NAME,
                 x=x_gauss,
                 y=y_gauss,
                 )
        ]
    )


def analysis_function(topography, funcname_profile, funcname_area, name, xlabel, ylabel, xname, yname, aname, xunit,
                      yunit, **kwargs):
    # Get low level topography from SurfaceTopography model
    topography = topography.topography()

    func = getattr(topography, funcname_profile)
    r, A = func(**kwargs)

    # Remove NaNs
    r = r[np.isfinite(A)]
    A = A[np.isfinite(A)]

    # Create dataset with unreliable data
    ru, Au = func(reliable=False, **kwargs)

    # Remove NaNs
    ru = ru[np.isfinite(Au)]
    Au = Au[np.isfinite(Au)]

    if topography.dim == 2:
        transpose_func = getattr(topography.transpose(), funcname_profile)
        areal_func = getattr(topography, funcname_area)

        r_T, A_T = transpose_func(**kwargs)
        r_2D, A_2D = areal_func(**kwargs)

        # Remove NaNs
        r_T = r_T[np.isfinite(A_T)]
        A_T = A_T[np.isfinite(A_T)]
        r_2D = r_2D[np.isfinite(A_2D)]
        A_2D = A_2D[np.isfinite(A_2D)]

        ru_T, Au_T = transpose_func(reliable=False, **kwargs)
        ru_2D, Au_2D = areal_func(reliable=False, **kwargs)

        # Remove NaNs
        ru_T = ru_T[np.isfinite(Au_T)]
        Au_T = Au_T[np.isfinite(Au_T)]
        ru_2D = ru_2D[np.isfinite(Au_2D)]
        Au_2D = Au_2D[np.isfinite(Au_2D)]

    #
    # Build series
    #
    series = [
        dict(name=xname,
             x=r,
             y=A,
             ),
    ]

    if topography.dim == 2:
        series += [
            dict(name=yname,
                 x=r_T,
                 y=A_T,
                 visible=False,  # We hide everything by default except for the first data series
                 ),
            dict(name=aname,
                 x=r_2D,
                 y=A_2D,
                 visible=False,
                 ),
        ]

    series += [
        dict(name='{} (incl. unreliable data)'.format(xname),
             x=ru,
             y=Au,
             visible=False,
             ),
    ]

    if topography.dim == 2:
        series += [
            dict(name='{} (incl. unreliable data)'.format(yname),
                 x=ru_T,
                 y=Au_T,
                 visible=False,
                 ),
            dict(name='{} (incl. unreliable data)'.format(aname),
                 x=ru_2D,
                 y=Au_2D,
                 visible=False,
                 ),
        ]

    # Unit for displaying ACF
    unit = topography.unit

    return dict(
        name=name,
        xlabel=xlabel,
        ylabel=ylabel,
        xunit=xunit.format(unit),
        yunit=yunit.format(unit),
        xscale='log',
        yscale='log',
        series=series)


def analysis_function_for_surface(surface, progress_recorder, funcname_profile, name, xlabel, ylabel, xname, xunit,
                                  yunit, **kwargs):
    """Calculate average variable bandwidth for a surface."""
    topographies = ContainerProxy(surface.topography_set.all())
    unit = suggest_length_unit(topographies)
    r, A = log_average(topographies, funcname_profile, unit,
                       progress_callback=lambda i, n: progress_recorder.set_progress(i + 1, n),
                       **kwargs)

    # Remove NaNs
    r = r[np.isfinite(A)]
    A = A[np.isfinite(A)]

    #
    # Build series
    #
    series = [dict(name=xname,
                   x=r,
                   y=A,
                   )]

    result = dict(
        name=name,
        xlabel=xlabel,
        ylabel=ylabel,
        xunit=xunit.format(unit),
        yunit=yunit.format(unit),
        xscale='log',
        yscale='log',
        series=series)

    return result


@register_implementation(name="Power spectrum", card_view_flavor='plot')
def power_spectrum(topography, window=None, progress_recorder=None, storage_prefix=None):
    """Calculate Power Spectrum for given topography."""
    # Get low level topography from SurfaceTopography model
    return analysis_function(topography,
                             'power_spectrum_from_profile',
                             'power_spectrum_from_area',
                             'Power-spectral density (PSD)',
                             'Wavevector',
                             'PSD',
                             '1D PSD along x',
                             '1D PSD along y',
                             'q/π × 2D PSD',
                             '{}⁻¹',
                             '{}³',
                             window=window)


@register_implementation(name="Power spectrum", card_view_flavor='plot')
def power_spectrum_for_surface(surface, window=None, progress_recorder=None, storage_prefix=None):
    """Calculate Power Spectrum for given topography."""
    # Get low level topography from SurfaceTopography model
    return analysis_function_for_surface(surface,
                                         progress_recorder,
                                         'power_spectrum_from_profile',
                                         'Power-spectral density (PSD)',
                                         'Wavevector',
                                         'PSD',
                                         '1D PSD along x',
                                         '{}⁻¹',
                                         '{}³',
                                         window=window)


@register_implementation(name="Autocorrelation", card_view_flavor='plot')
def autocorrelation(topography, progress_recorder=None, storage_prefix=None):
    return analysis_function(topography,
                             'autocorrelation_from_profile',
                             'autocorrelation_from_area',
                             'Autocorrelation (ACF)',
                             'Distance',
                             'ACF',
                             'Along x',
                             'Along y',
                             'Radial average',
                             '{}',
                             '{}²')


@register_implementation(name="Autocorrelation", card_view_flavor='plot')
def autocorrelation_for_surface(surface, progress_recorder=None, storage_prefix=None):
    return analysis_function_for_surface(surface,
                                         progress_recorder,
                                         'autocorrelation_from_profile',
                                         'Autocorrelation (ACF)',
                                         'Distance',
                                         'ACF',
                                         'Along x',
                                         '{}',
                                         '{}²')


@register_implementation(name="Variable bandwidth", card_view_flavor='plot')
def variable_bandwidth(topography, progress_recorder=None, storage_prefix=None):
    return analysis_function(topography,
                             'variable_bandwidth_from_profile',
                             'variable_bandwidth_from_area',
                             'Variable-bandwidth analysis',
                             'Bandwidth',
                             'RMS height',
                             'Profile decomposition along x',
                             'Profile decomposition along y',
                             'Areal decomposition',
                             '{}',
                             '{}')


@register_implementation(name="Variable bandwidth", card_view_flavor='plot')
def variable_bandwidth_for_surface(surface, progress_recorder=None, storage_prefix=None):
    return analysis_function_for_surface(surface,
                                         progress_recorder,
                                         'variable_bandwidth_from_profile',
                                         'Variable-bandwidth analysis',
                                         'Bandwidth',
                                         'RMS height',
                                         'Profile decomposition along x',
                                         '{}',
                                         '{}')


def scale_dependent_roughness_parameter(topography, progress_recorder, order_of_derivative, name, ylabel, xname, yname,
                                        xyfunc, xyname, yunit):
    topography = topography.topography()

    if topography.dim == 2:
        fac = 3
    else:
        fac = 1

    distances, rms_values_sq = topography.scale_dependent_statistical_property(
        lambda x, y=None: np.mean(x * x), n=order_of_derivative,
        progress_callback=lambda i, n: progress_recorder.set_progress(i + 1, fac * n))
    series = [dict(name=xname,
                   x=distances,
                   y=np.sqrt(rms_values_sq),
                   )]

    if topography.dim == 2:
        distances, rms_values_sq = topography.transpose().scale_dependent_statistical_property(
            lambda x, y=None: np.mean(x * x), n=order_of_derivative,
            progress_callback=lambda i, n: progress_recorder.set_progress(n + i + 1, 3 * n))
        series += [dict(name=yname,
                        x=distances,
                        y=np.sqrt(rms_values_sq),
                        visible=False,
                        )]

        distances, rms_values_sq = topography.transpose().scale_dependent_statistical_property(
            lambda x, y: np.mean(xyfunc(x, y)), n=order_of_derivative,
            progress_callback=lambda i, n: progress_recorder.set_progress(2 * n + i + 1, 3 * n))
        series += [dict(name=xyname,
                        x=distances,
                        y=np.sqrt(rms_values_sq),
                        visible=False,
                        )]

    unit = topography.unit
    return dict(
        name=name,
        xlabel='Distance',
        ylabel=ylabel,
        xunit=unit,
        yunit=yunit.format(unit),
        xscale='log',
        yscale='log',
        series=series)


def scale_dependent_roughness_parameter_for_surface(surface, progress_recorder, order_of_derivative, name, ylabel,
                                                    xname, yunit):
    topographies = ContainerProxy(surface.topography_set.all())
    unit = suggest_length_unit(topographies)
    # Factor of two for curvature
    distances, rms_values_sq = scale_dependent_statistical_property(
        topographies, lambda x, y=None: np.mean(x * x), n=order_of_derivative, unit=unit,
        progress_callback=lambda i, n: progress_recorder.set_progress(i + 1, n))
    series = [dict(name=xname,
                   x=distances,
                   y=np.sqrt(rms_values_sq),
                   )]

    return dict(
        name=name,
        xlabel='Distance',
        ylabel=ylabel,
        xunit=unit,
        yunit=yunit.format(unit),
        xscale='log',
        yscale='log',
        series=series)


@register_implementation(name="Scale-dependent slope", card_view_flavor='plot')
def scale_dependent_slope(topography, progress_recorder=None, storage_prefix=None):
    return scale_dependent_roughness_parameter(
        topography,
        progress_recorder,
        1,
        'Scale-dependent slope',
        'Slope',
        'Slope in x-direction',
        'Slope in y-direction',
        lambda x, y: x * x + y * y,
        'Gradient',
        '1')


@register_implementation(name="Scale-dependent slope", card_view_flavor='plot')
def scale_dependent_slope_for_surface(surface, progress_recorder=None, storage_prefix=None):
    return scale_dependent_roughness_parameter_for_surface(
        surface,
        progress_recorder,
        1,
        'Scale-dependent slope',
        'Slope',
        'Slope in x-direction',
        '1')


@register_implementation(name="Scale-dependent curvature", card_view_flavor='plot')
def scale_dependent_curvature(topography, progress_recorder=None, storage_prefix=None):
    return scale_dependent_roughness_parameter(
        topography,
        progress_recorder,
        2,
        'Scale-dependent curvature',
        'Curvature',
        'Curvature in x-direction',
        'Curvature in y-direction',
        lambda x, y: (x + y) ** 2 / 4,
        '1/2 Laplacian',
        '{}⁻¹')


@register_implementation(name="Scale-dependent curvature", card_view_flavor='plot')
def scale_dependent_curvature_for_surface(surface, progress_recorder=None, storage_prefix=None):
    return scale_dependent_roughness_parameter_for_surface(
        surface,
        progress_recorder,
        2,
        'Scale-dependent curvature',
        'Curvature',
        'Curvature in x-direction',
        '{}⁻¹')


def _next_contact_step(system, history=None, pentol=None, maxiter=None):
    """
    Run a full contact calculation. Try to guess displacement such that areas
    are equally spaced on a log scale.

    Parameters
    ----------
    system : ContactMechanics.Systems.SystemBase
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
    heights = topography.heights()

    # Find max, min and mean heights
    top = np.max(heights)
    middle = np.mean(heights)
    bot = np.min(heights)

    if history is None:
        step = 0
    else:
        mean_displacements, mean_gaps, mean_pressures, total_contact_areas, converged = history
        step = len(mean_displacements)

    if step == 0:
        mean_displacements = []
        mean_gaps = []
        mean_pressures = []
        total_contact_areas = []
        converged = np.array([], dtype=bool)

        mean_displacement = -middle
    elif step == 1:
        mean_displacement = -top + 0.01 * (top - middle)
    else:
        # Intermediate sort by area
        sorted_disp, sorted_area = np.transpose(
            sorted(zip(mean_displacements, total_contact_areas), key=lambda x: x[1]))

        ref_area = np.log10(np.array(sorted_area + 1 / np.prod(topography.nb_grid_pts)))
        darea = np.append(ref_area[1:] - ref_area[:-1], -ref_area[-1])
        i = np.argmax(darea)
        if i == step - 1:
            mean_displacement = bot + 2 * (sorted_disp[-1] - bot)
        else:
            mean_displacement = (sorted_disp[i] + sorted_disp[i + 1]) / 2

    opt = system.minimize_proxy(offset=mean_displacement, pentol=pentol, maxiter=maxiter)
    force_xy = opt.jac
    displacement_xy = opt.x[:force_xy.shape[0], :force_xy.shape[1]]
    mean_displacements = np.append(mean_displacements, [mean_displacement])
    mean_gaps = np.append(mean_gaps, [np.mean(displacement_xy) - middle - mean_displacement])
    mean_load = force_xy.sum() / np.prod(topography.physical_sizes)
    mean_pressures = np.append(mean_pressures, [mean_load])
    total_contact_area = (force_xy > 0).sum() / np.prod(topography.nb_grid_pts)
    total_contact_areas = np.append(total_contact_areas, [total_contact_area])
    converged = np.append(converged, np.array([opt.success], dtype=bool))

    area_per_pt = substrate.area_per_pt
    pressure_xy = force_xy / area_per_pt
    gap_xy = displacement_xy - topography.heights() - opt.offset
    gap_xy[gap_xy < 0.0] = 0.0

    contacting_points_xy = force_xy > 0

    return displacement_xy, gap_xy, pressure_xy, contacting_points_xy, \
           mean_displacement, mean_load, total_contact_area, \
           (mean_displacements, mean_gaps, mean_pressures, total_contact_areas, converged)


def _contact_at_given_load(system, external_force, history=None, pentol=None, maxiter=None):
    """
    Run a full contact calculation at a given external load.

    Parameters
    ----------
    system : ContactMechanics.Systems.SystemBase
        The contact mechanical system.
    external_force : float
        The force pushing the surfaces together.
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
    heights = topography.heights()

    # Find max, min and mean heights
    top = np.max(heights)
    middle = np.mean(heights)
    bot = np.min(heights)

    if history is None:
        mean_displacements = []
        mean_gaps = []
        mean_pressures = []
        total_contact_areas = []
        converged = np.array([], dtype=bool)
    if history is not None:
        mean_displacements, mean_gaps, mean_pressures, total_contact_areas, converged = history

    opt = system.minimize_proxy(external_force=external_force, pentol=pentol, maxiter=maxiter)
    force_xy = opt.jac
    displacement_xy = opt.x[:force_xy.shape[0], :force_xy.shape[1]]
    mean_displacements = np.append(mean_displacements, [opt.offset])
    mean_gaps = np.append(mean_gaps, [np.mean(displacement_xy) - middle - opt.offset])
    mean_load = force_xy.sum() / np.prod(topography.physical_sizes)
    mean_pressures = np.append(mean_pressures, [mean_load])
    total_contact_area = (force_xy > 0).sum() / np.prod(topography.nb_grid_pts)
    total_contact_areas = np.append(total_contact_areas, [total_contact_area])
    converged = np.append(converged, np.array([opt.success], dtype=bool))

    area_per_pt = substrate.area_per_pt
    pressure_xy = force_xy / area_per_pt
    gap_xy = displacement_xy - topography.heights() - opt.offset
    gap_xy[gap_xy < 0.0] = 0.0

    contacting_points_xy = force_xy > 0

    return displacement_xy, gap_xy, pressure_xy, contacting_points_xy, \
           opt.offset, mean_load, total_contact_area, \
           (mean_displacements, mean_gaps, mean_pressures, total_contact_areas, converged)


@register_implementation(name="Contact mechanics", card_view_flavor='contact mechanics')
def contact_mechanics(topography, substrate_str=None, hardness=None, nsteps=10,
                      pressures=None, maxiter=100, progress_recorder=None, storage_prefix=None):
    """
    Note that `loads` is a list of pressures if the substrate is periodic and a list of forces otherwise.

    :param topography:
    :param substrate_str: one of ['periodic', 'nonperiodic', None ]; if None, choose from topography's 'is_periodic' flag
    :param hardness: float value (unit: E*)
    :param nsteps: int or None, if None, "loads" must be given a list
    :param pressures: list of floats or None, if None, choose pressures automatically by using given number of steps (nsteps)
    :param maxiter: int, maximum number of iterations unless convergence
    :param progress_recorder:
    :param storage_prefix:
    :return:
    """

    # Get low level topography from SurfaceTopography model
    topography = topography.topography()

    if topography.dim == 1:
        raise IncompatibleTopographyException("Contact mechanics not implemented for line scans.")

    #
    # Choose substrate str from 'is_periodic' flag, if not given
    #
    if substrate_str is None:
        substrate_str = 'periodic' if topography.is_periodic else 'nonperiodic'

    #
    # Check whether either loads or nsteps is given, but not both
    #
    if (nsteps is None) and (pressures is None):
        raise ValueError("Either 'nsteps' or 'pressures' must be given for contact mechanics calculation.")

    if (nsteps is not None) and (pressures is not None):
        raise ValueError("Both 'nsteps' and 'pressures' are given. One must be None.")

    kwargs_limits = settings.CONTACT_MECHANICS_KWARGS_LIMITS
    #
    # Check some limits for number of pressures, maxiter, and nsteps
    # (same should be used in HTML page and checked by JS)
    #
    if nsteps and ((nsteps < kwargs_limits['nsteps']['min']) or (nsteps > kwargs_limits['nsteps']['max'])):
        raise ValueError(f"Invalid value for 'nsteps': {nsteps}")
    if pressures and ((len(pressures) < 1) or (len(pressures) > kwargs_limits['pressures']['maxlen'])):
        raise ValueError(f"Invalid number of pressures given: {len(pressures)}")
    if (maxiter < kwargs_limits['maxiter']['min']) or (maxiter > kwargs_limits['maxiter']['max']):
        raise ValueError(f"Invalid value for 'maxiter': {maxiter}")

    # Conversion of force units
    force_conv = np.prod(topography.physical_sizes)

    #
    # Some constants
    #
    min_pentol = 1e-12  # lower bound for the penetration tolerance

    if (hardness is not None) and (hardness > 0):
        topography = PlasticTopography(topography, hardness)

    half_space_factory = dict(periodic=PeriodicFFTElasticHalfSpace,
                              nonperiodic=FreeFFTElasticHalfSpace)

    half_space_kwargs = {}

    substrate = half_space_factory[substrate_str](topography.nb_grid_pts, 1.0, topography.physical_sizes,
                                                  **half_space_kwargs)

    system = make_system(substrate, topography)

    # Heuristics for the possible tolerance on penetration.
    # This is necessary because numbers can vary greatly
    # depending on the system of units.
    rms_height = topography.rms_height_from_area()
    pentol = rms_height / (10 * np.mean(topography.nb_grid_pts))
    pentol = max(pentol, min_pentol)

    netcdf_format = 'NETCDF4'

    data_paths = []  # collect in _next_contact_step?

    if pressures is not None:
        nsteps = len(pressures)

    history = None
    for i in range(nsteps):
        if pressures is None:
            displacement_xy, gap_xy, pressure_xy, contacting_points_xy, \
            mean_displacement, mean_pressure, total_contact_area, history = \
                _next_contact_step(system, history=history, pentol=pentol, maxiter=maxiter)
        else:
            displacement_xy, gap_xy, pressure_xy, contacting_points_xy, \
            mean_displacement, mean_pressure, total_contact_area, history = \
                _contact_at_given_load(system, pressures[i] * force_conv, history=history, pentol=pentol,
                                       maxiter=maxiter)

        #
        # Save displacement_xy, gap_xy, pressure_xy and contacting_points_xy
        # to storage, will be retrieved later for visualization
        #
        pressure_xy = xr.DataArray(pressure_xy, dims=('x', 'y'))  # maybe define coordinates
        gap_xy = xr.DataArray(gap_xy, dims=('x', 'y'))
        displacement_xy = xr.DataArray(displacement_xy, dims=('x', 'y'))
        contacting_points_xy = xr.DataArray(contacting_points_xy, dims=('x', 'y'))

        dataset = xr.Dataset({'pressure': pressure_xy,
                              'contacting_points': contacting_points_xy,
                              'gap': gap_xy,
                              'displacement': displacement_xy})  # one dataset per analysis step: smallest unit to retrieve
        dataset.attrs['mean_pressure'] = mean_pressure
        dataset.attrs['total_contact_area'] = total_contact_area
        dataset.attrs['type'] = substrate_str
        if hardness:
            dataset.attrs['hardness'] = hardness  # TODO how to save hardness=None? Not possible in netCDF

        with tempfile.NamedTemporaryFile(prefix='analysis-') as tmpfile:
            dataset.to_netcdf(tmpfile.name, format=netcdf_format)

            storage_path = storage_prefix + "result-step-{}.nc".format(i)
            tmpfile.seek(0)
            storage_path = default_storage.save(storage_path, File(tmpfile))
            data_paths.append(storage_path)

        progress_recorder.set_progress(i + 1, nsteps)

    mean_displacement, mean_gap, mean_pressure, total_contact_area, converged = history

    mean_pressure = np.array(mean_pressure)
    total_contact_area = np.array(total_contact_area)
    mean_displacement = np.array(mean_displacement)
    mean_gap = np.array(mean_gap)
    converged = np.array(converged)

    data_paths = np.array(data_paths, dtype='str')
    sort_order = np.argsort(mean_pressure)

    return dict(
        name='Contact mechanics',
        area_per_pt=substrate.area_per_pt,
        maxiter=maxiter,
        min_pentol=min_pentol,
        mean_pressures=mean_pressure[sort_order],
        total_contact_areas=total_contact_area[sort_order],
        mean_displacements=mean_displacement[sort_order] / rms_height,
        mean_gaps=mean_gap[sort_order] / rms_height,
        converged=converged[sort_order],
        data_paths=data_paths[sort_order],
        effective_kwargs=dict(
            substrate_str=substrate_str,
            hardness=hardness,
            nsteps=nsteps,
            pressures=pressures,
            maxiter=maxiter,
        )
    )


@register_implementation(name="Roughness parameters", card_view_flavor='roughness parameters')
def roughness_parameters(topography, progress_recorder=None, storage_prefix=None):
    """Calculate roughness parameters for given topography.

    Parameters
    ----------
    topography: topobank.manager.models.Topography
    progress_recorder: celery_progress.backend.ProgressRecorder or None
    storage_prefix: str or None

    Returns
    -------
    list of dicts where each dict has keys

     quantity, e.g. 'RMS height' or 'RMS gradient'
     direction, e.g. 'x' or None
     from, e.g. 'profile (1D)' or 'area (2D)' or ''
     symbol, e.g. 'Sq' or ''
     value, a number or NaN
     unit, e.g. 'nm'
    """

    # Get low level topography from SurfaceTopography model
    topography = topography.topography()

    # noinspection PyBroadException
    try:
        unit = topography.unit
        inverse_unit = '{}⁻¹'.format(unit)
    except KeyError:
        unit = None
        inverse_unit = None

    is_2D = topography.dim == 2
    if not is_2D and not (topography.dim == 1):
        raise ValueError("This analysis function can only handle 1D or 2D topographies.")

    FROM_1D = 'profile (1D)'
    FROM_2D = 'area (2D)'

    #
    # RMS height
    #
    result = [
        {
            'quantity': 'RMS height',
            'from': FROM_1D,
            'symbol': 'Rq',
            'direction': 'x',
            'value': topography.rms_height_from_profile(),
            'unit': unit,
        }
    ]
    if is_2D:
        result.extend([
            {
                'quantity': 'RMS height',
                'from': FROM_1D,
                'symbol': 'Rq',
                'direction': 'y',
                'value': topography.transpose().rms_height_from_profile(),
                'unit': unit,
            },
            {
                'quantity': 'RMS height',
                'from': FROM_2D,
                'symbol': 'Sq',
                'direction': None,
                'value': topography.rms_height_from_area(),
                'unit': unit,
            },
        ])
    #
    # RMS curvature
    #
    if is_2D:
        result.extend([
            {
                'quantity': 'RMS curvature',
                'from': FROM_1D,
                'symbol': '',
                'direction': 'y',
                'value': topography.transpose().rms_curvature_from_profile(),
                'unit': inverse_unit,
            },
            {
                'quantity': 'RMS curvature',
                'from': FROM_2D,
                'symbol': '',
                'direction': None,
                'value': topography.rms_curvature_from_area(),
                'unit': inverse_unit,
            }
        ])

    # RMS curvature in x direction is needed for 1D and 2D
    result.append({
        'quantity': 'RMS curvature',
        'from': FROM_1D,
        'symbol': '',
        'direction': 'x',
        'value': topography.rms_curvature_from_profile(),
        'unit': inverse_unit,
    })

    #
    # RMS gradient/slope
    #
    result.extend([
        {
            'quantity': 'RMS slope',
            'from': FROM_1D,
            'symbol': 'R&Delta;q',
            'direction': 'x',
            'value': topography.rms_slope_from_profile(),  # x direction
            'unit': 1,
        }
    ])
    if is_2D:
        result.extend([
            {
                'quantity': 'RMS slope',
                'from': FROM_1D,
                'symbol': 'R&Delta;q',  # HTML
                'direction': 'y',
                'value': topography.transpose().rms_slope_from_profile(),  # y direction
                'unit': 1,
            },
            {
                'quantity': 'RMS gradient',
                'from': FROM_2D,
                'symbol': '',
                'direction': None,
                'value': topography.rms_gradient(),
                'unit': 1,
            },
        ])

    #
    # Bandwidth (pixel_size, scan_size), see GH #677
    #
    lower_bound, upper_bound = topography.bandwidth()
    result.extend([
        {
            'quantity': 'Bandwidth: lower bound',
            'from': FROM_2D if is_2D else FROM_1D,
            'symbol': '',
            'direction': None,
            'value': lower_bound,
            'unit': unit,
        },
        {
            'quantity': 'Bandwidth: upper bound',
            'from': FROM_2D if is_2D else FROM_1D,
            'symbol': '',
            'direction': None,
            'value': upper_bound,
            'unit': unit,
        },
    ])

    return result


def topography_analysis_function_for_tests(topography, a=1, b="foo"):
    """This function can be registered for tests."""
    return {'name': 'Test result for test function called for topography {}.'.format(topography),
            'xunit': 'm',
            'yunit': 'm',
            'xlabel': 'x',
            'ylabel': 'y',
            'series': [
                dict(
                    name='Fibonacci series',
                    x=np.array((1, 2, 3, 4, 5, 6, 7, 8)),
                    y=np.array((0, 1, 1, 2, 3, 5, 8, 13)),
                    std_err_y=np.zeros(8),
                )
            ],
            'comment': f"a is {a} and b is {b}"}


def surface_analysis_function_for_tests(surface, a=1, c="bar"):
    """This function can be registered for tests."""
    return {'name': 'Test result for test function called for surface {}.'.format(surface),
            'xunit': 'm',
            'yunit': 'm',
            'xlabel': 'x',
            'ylabel': 'y',
            'series': [],
            'comment': f"a is {a} and c is {c}"}
