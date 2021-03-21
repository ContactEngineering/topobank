"""
Implementations of analysis functions for topographies and surfaces.

The first argument is either a Topography or Surface instance (model).
"""
from django.core.files.storage import default_storage
from django.core.files import File
from django.conf import settings

import xarray as xr
import numpy as np
import tempfile
from pint import UnitRegistry, UndefinedUnitError
from scipy.interpolate import interp1d
import scipy.stats

from SurfaceTopography import Topography, PlasticTopography
from ContactMechanics import PeriodicFFTElasticHalfSpace, FreeFFTElasticHalfSpace, make_system

import topobank.manager.models  # will be used to evaluate model classes
from .registry import AnalysisFunctionRegistry


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


def _reasonable_bins_argument(topography):
    """Returns a reasonable 'bins' argument for np.histogram for given topography's heights.

    :param topography: Line scan or topography from SurfaceTopography module
    :return: argument for 'bins' argument of np.histogram
    """
    if topography.is_uniform:
        return int(np.sqrt(np.prod(topography.nb_grid_pts)) + 1.0)
    else:
        return int(np.sqrt(np.prod(len(topography.positions()))) + 1.0) # TODO discuss whether auto or this
        # return 'auto'


class IncompatibleTopographyException(Exception):
    """Raise this exception in case a function cannot handle a topography.

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


@register_implementation(name="Height Distribution", card_view_flavor='plot')
def height_distribution(topography, bins=None, wfac=5, progress_recorder=None, storage_prefix=None):

    # Get low level topography from SurfaceTopography model
    topography = topography.topography()

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
            dict(name='RMS height',
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

    if arr_max-arr_min < 5e-8:
        hist_range = (arr_min-1e-3, arr_max+1e-3)
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
    rms = np.sqrt((arr**2).mean())

    hist, bin_edges = np.histogram(arr, bins=bins, density=True,
                                   range=_reasonable_histogram_range(arr))

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
            dict(name=f'RMS {quantity} ({label})',
                 x=x_gauss,
                 y=y_gauss)
        )

    return scalars, series


@register_implementation(name="Slope Distribution", card_view_flavor='plot')
def slope_distribution(topography, bins=None, wfac=5, progress_recorder=None, storage_prefix=None):

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


@register_implementation(name="Curvature Distribution", card_view_flavor='plot')
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
    rms_curv = topography.rms_curvature()

    hist_arr = np.ma.compressed(curv)

    hist, bin_edges = np.histogram(hist_arr, bins=bins,
                                   range=_reasonable_histogram_range(hist_arr),
                                   density=True)

    minval = mean_curv - wfac * rms_curv
    maxval = mean_curv + wfac * rms_curv
    x_gauss = np.linspace(minval, maxval, 1001)
    y_gauss = np.exp(-(x_gauss - mean_curv) ** 2 / (2 * rms_curv ** 2)) / (np.sqrt(2 * np.pi) * rms_curv)

    unit = topography.info['unit']
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
            dict(name='RMS curvature',
                 x=x_gauss,
                 y=y_gauss,
                 )
        ]
    )


@register_implementation(name="Power Spectrum", card_view_flavor='plot')
def power_spectrum(topography, window=None, tip_radius=None, progress_recorder=None, storage_prefix=None):

    # Get low level topography from SurfaceTopography model
    topography = topography.topography()

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
        sx, sy = topography.physical_sizes
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


def average_series_list(series_list, num_points=100, xscale='linear'):
    """Given a list of series dicts, return a dict for an average series.

    Parameters
    ----------
    series_list: list of dicts

                Each dict represents a function and should have the following keys:

                {
                    'name': str, name of series, must be equal for all given series!
                    'x': np.array with x values, 1D
                    'y': np.array with y values, same length as 'x'
                }

                All numbers must be given in the same units.
    num_points: int
                Number of points in results
    xscale: str
                Scaling of x axis on which the sampling is done. Can be 'linear' or 'log'.
                If given 'log', the incoming data is filtered such that x values are always
                positive.

    Result
    ------

    Also a series dict

    {
        'name': str, common name of all series
        'x': np.array, points spanning range of all x points in input series (only positive if xscale=='log')
        'y': np.array, average values for all relevant points in input series when using linear interpolation
    }

    """
    if len(series_list) == 0:
        raise ValueError("At least one series must be given for averaging!")

    # Check for common name
    name_set = set(s['name'] for s in series_list)
    if len(name_set) > 1:
        raise ValueError("Series names must be unique!")
    common_name = name_set.pop()

    # x values must not be empty
    for s in series_list:
        if s['x'].size == 0:
            raise ValueError("Empty series given for averaging!")

    #
    # If xscale not 'linear', the sampling for interpolation
    # is done on another scale, e.g. log scale. For log scale, only
    # positive x values are allowed.
    #
    spacing_funcs = {
        'linear': np.linspace,
        'log': np.geomspace
    }

    if xscale == 'log':
        for s in series_list:
            positive_idx = s['x'] > 0
            s['x'] = s['x'][positive_idx]
            s['y'] = s['y'][positive_idx]

    #
    # Find out range of x values for result
    #
    min_x = min(min(s['x']) for s in series_list)
    max_x = max(max(s['x']) for s in series_list)


    try:
        av_x = spacing_funcs[xscale](min_x, max_x, num_points)
    except KeyError:
        raise ValueError(f"Averaging for xscale '{xscale}' not yet implemented.")

    # do linear interpolation for each series and average y values of all relevant series
    interpol_y_list = []
    for s in series_list:
        # we interpolate in the scale of original data (not log scale)
        interpol = interp1d(s['x'], s['y'], bounds_error=False)  # inserts NaN outside of boundaries
        interp_y = interpol(av_x)
        interpol_y_list.append(interp_y)

    av_y = np.nanmean(interpol_y_list, axis=0)  # ignores NaNs generated by interpolation
    std_err_y = scipy.stats.sem(interpol_y_list, nan_policy='omit')
    # a masked value in result of sem() only appears if there is for a given index only one
    # number (others are nan).

    return {
        'name': common_name,
        'x': av_x,
        'y': av_y,
        'std_err_y': std_err_y
    }


def average_results_for_surface(surface, topo_analysis_func, num_points=100,
                                progress_recorder=None, storage_prefix=None, **kwargs):
    """Generic analysis function for average over topographies

    Parameters
        surface: Surface instance
        topo_analysis_func: function
            analysis function which should be called on each topography
            using the **kwargs arguments.
        progress_recorder: ProgressRecorder instance
            currently used only on top level, not passed to topography analysis
        storage_prefix:
            also passed to topo_analysis_func
        kwargs: dict
            other keyword arguments passed to topo_analysis_func
    Returns:
        dict with

        {
            'xunit': str,
            'yunit': str,
            'series': sequence of series with results
        }

        This dict can be used to build the full result dict

    Currently this only meant to be used with function returning results for xscale='log'
    like power_spectrum or autocorrelation (could be generalized).
    """
    topographies = surface.topography_set
    num_topographies = topographies.count()

    topo_result_series = {}  # key: series name, value: list of dict's, one for each result series

    ureg = UnitRegistry()
    xunit = None
    yunit = None

    num_steps = num_topographies + 1  # averaging counted as extra step

    #
    # We have to process each series name individually, so we first collect the series
    # for each series name. Each series is also scaled, in order to use common units.
    # When scaling the series, we have to take into account that the
    # series might already been scaled because of a log-log plot.
    #
    for topo_idx, topo in enumerate(topographies.all()):
        topo_result = topo_analysis_func(topo, storage_prefix=storage_prefix, **kwargs)

        if xunit is None:
            xunit = topo_result['xunit']
            yunit = topo_result['yunit']
            xunit_factor = 1
            yunit_factor = 1
        else:
            xunit_factor = ureg.convert(1, topo_result['xunit'], xunit)
            yunit_factor = ureg.convert(1, topo_result['yunit'], yunit)

        for s in topo_result['series']:
            series_name = s['name']
            if series_name not in topo_result_series:
                topo_result_series[series_name] = []
            scaled_series = {
                'name': s['name'],
                'x': s['x'] * xunit_factor,
                'y': s['y'] * yunit_factor,
            }
            topo_result_series[series_name].append(scaled_series)
        if progress_recorder:
            progress_recorder.set_progress(topo_idx + 1, num_steps)

    result_series = []

    for series_list in topo_result_series.values():
        result_series.append(average_series_list(series_list, num_points=num_points, xscale='log'))
    if progress_recorder:
        progress_recorder.set_progress(num_steps, num_steps)

    return dict(
        xunit=xunit,
        yunit=yunit,
        series=result_series
    )


@register_implementation(name="Power Spectrum", card_view_flavor='plot')
def power_spectrum_for_surface(surface, window=None, tip_radius=None, num_points=100,
                               progress_recorder=None, storage_prefix=None):
    """Calculate average power spectrum for a surface."""

    func_kwargs = dict(
        window=window,
        tip_radius=tip_radius,
        storage_prefix=storage_prefix
    )
    result = average_results_for_surface(surface, topo_analysis_func=power_spectrum,
                                         num_points=num_points, progress_recorder=progress_recorder,
                                         **func_kwargs)

    result.update(dict(
        name='Power-spectral density (PSD)',
        xlabel='Wavevector',
        ylabel='PSD',
        xscale='log',
        yscale='log',
    ))

    return result


@register_implementation(name="Autocorrelation", card_view_flavor='plot')
def autocorrelation(topography, progress_recorder=None, storage_prefix=None):

    # Get low level topography from SurfaceTopography model
    topography = topography.topography()

    if topography.dim == 2:
        sx, sy = topography.physical_sizes
        transposed_topography = Topography(topography.heights().T, physical_sizes=(sy, sx),
                                           periodic=topography.is_periodic)
        r_T, A_T = transposed_topography.autocorrelation_1D()
        r_2D, A_2D = topography.autocorrelation_2D()

        # Truncate ACF at half the system size
        s = min(sx, sy) / 2
    else:
        s, = topography.physical_sizes

    if topography.is_uniform:
        r, A = topography.autocorrelation_1D()
    else:
        # Work around. The implementation for non-uniform line scans is very slow. Map onto a uniform grid.
        x, h = topography.positions_and_heights()
        min_dist = np.min(np.diff(x))
        if min_dist <= 0:
            raise RuntimeError('Positions not sorted')
        else:
            n = min(100000, 10 * int(s / min_dist))
        r, A = topography.to_uniform(n, 0).autocorrelation_1D()
        r = r[::10]
        A = A[::10]

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
        series = [
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


@register_implementation(name="Autocorrelation", card_view_flavor='plot')
def autocorrelation_for_surface(surface, num_points=100,
                                progress_recorder=None, storage_prefix=None):
    """Calculate average autocorrelation for a surface."""
    result = average_results_for_surface(surface, topo_analysis_func=autocorrelation,
                                         num_points=num_points, progress_recorder=progress_recorder,
                                         storage_prefix=storage_prefix)

    result.update(dict(
        name='Height-difference autocorrelation function (ACF)',
        xlabel='Distance',
        ylabel='ACF',
        xscale='log',
        yscale='log',
    ))

    return result


@register_implementation(name="Scale-dependent Slope", card_view_flavor='plot')
def scale_dependent_slope(topography, progress_recorder=None, storage_prefix=None):

    return_dict = autocorrelation(topography, progress_recorder=progress_recorder,
                                  storage_prefix=storage_prefix)

    for dataset in return_dict['series']:
        x = dataset['x']
        y = dataset['y']
        # Avoid division by zero
        m = abs(x) > 1e-12
        dataset['x'] = x[m]
        dataset['y'] = np.sqrt(2 * y[m]) / x[m]
    return_dict['name'] = 'Scale-dependent slope'
    return_dict['ylabel'] = 'Slope'
    return_dict['yunit'] = ''

    return return_dict


@register_implementation(name="Scale-dependent Slope", card_view_flavor='plot')
def scale_dependent_slope_for_surface(surface, num_points=100,
                                      progress_recorder=None, storage_prefix=None):
    """Calculate average autocorrelation for a surface."""
    result = average_results_for_surface(surface, topo_analysis_func=scale_dependent_slope,
                                         num_points=num_points, progress_recorder=progress_recorder,
                                         storage_prefix=storage_prefix)

    result.update(dict(
        name='Scale-dependent slope',
        xlabel='Distance',
        ylabel='Slope',
        xscale='log',
        yscale='log',
    ))

    return result


@register_implementation(name="Variable Bandwidth", card_view_flavor='plot')
def variable_bandwidth(topography, progress_recorder=None, storage_prefix=None):

    # Get low level topography from SurfaceTopography model
    topography = topography.topography()

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


@register_implementation(name="Variable Bandwidth", card_view_flavor='plot')
def variable_bandwidth_for_surface(surface, num_points=100,
                                   progress_recorder=None, storage_prefix=None):
    """Calculate average variable bandwidth for a surface."""
    result = average_results_for_surface(surface, topo_analysis_func=variable_bandwidth,
                                         num_points=num_points, progress_recorder=progress_recorder,
                                         storage_prefix=storage_prefix)
    result.update(dict(
        name='Variable-bandwidth analysis',
        xlabel='Bandwidth',
        ylabel='RMS Height',
        xscale='log',
        yscale='log',
    ))

    return result



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
        sorted_disp, sorted_area = np.transpose(sorted(zip(mean_displacements, total_contact_areas), key=lambda x:x[1]))

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


@register_implementation(name="Contact Mechanics", card_view_flavor='contact mechanics')
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
    if (maxiter<kwargs_limits['maxiter']['min']) or (maxiter > kwargs_limits['maxiter']['max']):
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
    rms_height = topography.rms_height()
    pentol = rms_height / (10 * np.mean(topography.nb_grid_pts))
    pentol = max(pentol, min_pentol)

    netcdf_format = 'NETCDF4'

    data_paths = [] # collect in _next_contact_step?

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
                _contact_at_given_load(system, pressures[i]*force_conv, history=history, pentol=pentol, maxiter=maxiter)

        #
        # Save displacement_xy, gap_xy, pressure_xy and contacting_points_xy
        # to storage, will be retrieved later for visualization
        #
        pressure_xy = xr.DataArray(pressure_xy, dims=('x', 'y')) # maybe define coordinates
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

            storage_path = storage_prefix+"result-step-{}.nc".format(i)
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
        mean_displacements=mean_displacement[sort_order]/rms_height,
        mean_gaps=mean_gap[sort_order]/rms_height,
        converged=converged[sort_order],
        data_paths=data_paths[sort_order],
        effective_kwargs = dict(
            substrate_str=substrate_str,
            hardness=hardness,
            nsteps=nsteps,
            pressures=pressures,
            maxiter=maxiter,
        )
    )


@register_implementation(name="RMS Values", card_view_flavor='rms table')
def rms_values(topography, progress_recorder=None, storage_prefix=None):
    """Just calculate RMS values for given topography.

    Parameters
    ----------
    topography: topobank.manager.models.Topography
    progress_recorder: celery_progress.backend.ProgressRecorder or None
    storage_prefix: str or None

    Returns
    -------
    list of dicts where each dict has keys

     quantity
     direction
     value
     unit
    """

    # Get low level topography from SurfaceTopography model
    topography = topography.topography()

    try:
        unit = topography.info['unit']
        inverse_unit = '{}⁻¹'.format(unit)
    except:
        unit = None
        inverse_unit = None

    def rms_slope_from_der(der):
        der = der.flatten()
        return np.sqrt(((der**2).mean()))

    result = [
        {
            'quantity': 'RMS Height',
            'direction': None,
            'value': topography.rms_height(),
            'unit': unit,
        },
        {
            'quantity': 'RMS Curvature',
            'direction': None,
            'value': topography.rms_curvature(),
            'unit': inverse_unit,
        },
    ]

    if topography.dim == 2:
        dh_dx, dh_dy = topography.derivative(n=1)
        result.extend([
            {
                'quantity': 'RMS Slope',
                'direction': 'x',
                'value': rms_slope_from_der(dh_dx),
                'unit': 1,
            },
            {
                'quantity': 'RMS Slope',
                'direction': 'y',
                'value': rms_slope_from_der(dh_dy),
                'unit': 1,
            }
        ])
    elif topography.dim == 1:
        dh_dx = topography.derivative(n=1)
        result.extend([
            {
                'quantity': 'RMS Slope',
                'direction': 'x',
                'value': rms_slope_from_der(dh_dx),
                'unit': 1,
            }
        ])
    else:
        raise ValueError("This analysis function can only handle 1D or 2D topographies.")

    return result


def topography_analysis_function_for_tests(topography, a=1, b="foo"):
    """This function can be registered for tests."""
    return {'name': 'Test result for test function called for topography {}.'.format(topography),
            'xunit': 'm',
            'yunit': 'm',
            'xlabel': 'x',
            'ylabel': 'y',
            'series': [],
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

