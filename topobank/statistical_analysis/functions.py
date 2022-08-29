import numpy as np
from SurfaceTopography.Container.Averaging import log_average
from SurfaceTopography.Container.ScaleDependentStatistics import scale_dependent_statistical_property
from SurfaceTopography.Container.common import suggest_length_unit
from SurfaceTopography.Exceptions import CannotPerformAnalysisError

from topobank.analysis.functions import reasonable_bins_argument, wrap_series, \
    ReentrantTopographyException, make_alert_entry, ContainerProxy, ART_SERIES
from topobank.analysis.registry import register_implementation


ART_ROUGHNESS_PARAMETERS = "roughness parameters"

GAUSSIAN_FIT_SERIES_NAME = 'Gaussian fit'


@register_implementation(art=ART_SERIES, name="Height distribution")
def height_distribution(topography, bins=None, wfac=5, progress_recorder=None, storage_prefix=None):
    # Get low level topography from SurfaceTopography model
    topography = topography.topography()

    if bins is None:
        bins = reasonable_bins_argument(topography)

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

    series = [
        dict(name='Height distribution',
             x=(bin_edges[:-1] + bin_edges[1:]) / 2,
             y=hist,
             ),
        dict(name=GAUSSIAN_FIT_SERIES_NAME,
             x=x_gauss,
             y=y_gauss,
             )
    ]

    return dict(
        name='Height distribution',
        scalars={
            'Mean Height': dict(value=mean_height, unit=unit),
            'RMS Height': dict(value=rms_height, unit=unit),
        },
        xlabel='Height',
        ylabel='Probability density',
        xunit='' if unit is None else unit,
        yunit='' if unit is None else '{}⁻¹'.format(unit),
        series=wrap_series(series)
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


@register_implementation(art=ART_SERIES, name="Slope distribution")
def slope_distribution(topography, bins=None, wfac=5, progress_recorder=None, storage_prefix=None):
    """Calculates slope distribution for given topography."""
    # Get low level topography from SurfaceTopography model
    topography = topography.topography()

    if topography.is_reentrant:
        raise ReentrantTopographyException(
            'Slope distribution: Cannot calculate analysis function for reentrant measurements.')

    if bins is None:
        bins = reasonable_bins_argument(topography)

    scalars = {}
    series = []
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
        scalars.update(scalars_slope_x)
        series.extend(series_slope_x)

        #
        # Results for y direction
        #
        scalars_slope_y, series_slope_y = _moments_histogram_gaussian(dh_dy, bins=bins,
                                                                      topography=topography,
                                                                      wfac=wfac,
                                                                      quantity="slope", unit='1',
                                                                      label='y direction')
        scalars.update(scalars_slope_y)
        series.extend(series_slope_y)

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
        scalars.update(scalars_slope_x)
        series.extend(series_slope_x)
    else:
        raise ValueError("This analysis function can only handle 1D or 2D topographies.")

    return dict(
        name='Slope distribution',
        xlabel='Slope',
        ylabel='Probability density',
        xunit='1',
        yunit='1',
        scalars=scalars,
        series=wrap_series(series)
    )


@register_implementation(art=ART_SERIES, name="Curvature distribution")
def curvature_distribution(topography, bins=None, wfac=5, progress_recorder=None, storage_prefix=None):
    # Get low level topography from SurfaceTopography model
    topography = topography.topography()

    if topography.is_reentrant:
        raise ReentrantTopographyException(
            'Curvature distribution: Cannot calculate analysis function for reentrant measurements.')

    if bins is None:
        bins = reasonable_bins_argument(topography)

    #
    # Calculate the Laplacian
    #
    if topography.dim == 2:
        curv_x, curv_y = topography.derivative(n=2)
        curv = (curv_x + curv_y) / 2
    else:
        curv = topography.derivative(n=2)

    mean_curv = np.mean(curv)
    rms_curv = topography.rms_curvature_from_area() if topography.dim == 2 else topography.rms_curvature_from_profile()

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

    series = [
        dict(name='Curvature distribution',
             x=(bin_edges[:-1] + bin_edges[1:]) / 2,
             y=hist,
             ),
        dict(name=GAUSSIAN_FIT_SERIES_NAME,
             x=x_gauss,
             y=y_gauss,
             )
    ]

    return dict(
        name='Curvature distribution',
        scalars={
            'Mean Curvature': dict(value=mean_curv, unit=inverse_unit),
            'RMS Curvature': dict(value=rms_curv, unit=inverse_unit),
        },
        xlabel='Curvature',
        ylabel='Probability density',
        xunit=inverse_unit,
        yunit=unit,
        series=wrap_series(series)
    )


@register_implementation(art=ART_SERIES, name="Power spectrum")
def power_spectrum(topography, progress_recorder=None, storage_prefix=None, window=None,
                   nb_points_per_decade=10):
    """Calculate Power Spectrum for given topography."""
    # Get low level topography from SurfaceTopography model
    return _analysis_function(topography,
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
                              conv_2d_fac=1 / np.pi,
                              conv_2d_exponent=1,
                              window=window,
                              nb_points_per_decade=nb_points_per_decade,
                              storage_prefix=storage_prefix)


@register_implementation(art=ART_SERIES, name="Power spectrum")
def power_spectrum_for_surface(surface, progress_recorder=None, storage_prefix=None, window=None,
                               nb_points_per_decade=10):
    """Calculate Power Spectrum for given topography."""
    # Get low level topography from SurfaceTopography model

    return _analysis_function_for_surface(surface,
                                          progress_recorder,
                                         'power_spectrum_from_profile',
                                         'Power-spectral density (PSD)',
                                         'Wavevector',
                                         'PSD',
                                         '1D PSD along x',
                                         '{}⁻¹',
                                         '{}³',
                                          window=window,
                                          nb_points_per_decade=nb_points_per_decade,
                                          storage_prefix=storage_prefix)


@register_implementation(art=ART_SERIES, name="Autocorrelation")
def autocorrelation(topography, progress_recorder=None, storage_prefix=None, nb_points_per_decade=10):
    return _analysis_function(topography,
                             'autocorrelation_from_profile',
                             'autocorrelation_from_area',
                             'Height-difference autocorrelation function (ACF)',
                             'Distance',
                             'ACF',
                             'Along x',
                             'Along y',
                             'Radial average',
                             '{}',
                             '{}²',
                              nb_points_per_decade=nb_points_per_decade,
                              storage_prefix=storage_prefix)


@register_implementation(art=ART_SERIES, name="Autocorrelation")
def autocorrelation_for_surface(surface, progress_recorder=None, storage_prefix=None, nb_points_per_decade=10):
    return _analysis_function_for_surface(surface,
                                          progress_recorder,
                                         'autocorrelation_from_profile',
                                         'Height-difference autocorrelation function (ACF)',
                                         'Distance',
                                         'ACF',
                                         'Along x',
                                         '{}',
                                         '{}²',
                                          nb_points_per_decade=nb_points_per_decade,
                                          storage_prefix=storage_prefix)


@register_implementation(art=ART_SERIES, name="Variable bandwidth")
def variable_bandwidth(topography, progress_recorder=None, storage_prefix=None):
    return _analysis_function(topography,
                             'variable_bandwidth_from_profile',
                             'variable_bandwidth_from_area',
                             'Variable-bandwidth analysis',
                             'Bandwidth',
                             'RMS height',
                             'Profile decomposition along x',
                             'Profile decomposition along y',
                             'Areal decomposition',
                             '{}',
                             '{}',
                              storage_prefix=storage_prefix)


@register_implementation(art=ART_SERIES, name="Variable bandwidth")
def variable_bandwidth_for_surface(surface, progress_recorder=None, storage_prefix=None, nb_points_per_decade=10):
    return _analysis_function_for_surface(surface,
                                          progress_recorder,
                                         'variable_bandwidth_from_profile',
                                         'Variable-bandwidth analysis',
                                         'Bandwidth',
                                         'RMS height',
                                         'Profile decomposition along x',
                                         '{}',
                                         '{}',
                                          nb_points_per_decade=nb_points_per_decade,
                                          storage_prefix=storage_prefix)


def scale_dependent_roughness_parameter(topography, progress_recorder, order_of_derivative, name, ylabel, xname, yname,
                                        xyfunc, xyname, yunit, storage_prefix=None, **kwargs):
    topography_name = topography.name
    topography_url = topography.get_absolute_url()

    topography = topography.topography()

    series = []
    alerts = []

    if topography.is_reentrant:
        raise ReentrantTopographyException(
            '{}: Cannot calculate analysis function for reentrant measurements.'.format(name))

    if topography.dim == 2:
        nb_analyses = 6  # x-direction, y-direction, xy-direction (reliable + unreliable)
    else:
        nb_analyses = 2  # Just x-direction (reliable + unreliable)
    progress_offset = 0
    progress_callback = None if progress_recorder is None else \
        lambda i, n: progress_recorder.set_progress(progress_offset + i/n, nb_analyses)

    def process_series_reliable_unreliable(series_name, func_kwargs, is_reliable_visible=False):
        """Add series for reliable and unreliable data.

        Series with reliable data is only added if there is some reliable data.
        Series are added to `series` from out scope.

        Parameters
        ----------
        series_name: str
            name of the series
        func_kwargs: dict
            arguments for `topography.scale_dependent_statistical_property`
        is_reliable_visible: bool
            If True, the series for 'reliable=True' should be visible in the UI.
            Default is False.
        """
        nonlocal series, progress_offset
        try:
            distances, rms_values_sq = topography.scale_dependent_statistical_property(**func_kwargs)
            series += [dict(name=series_name,
                            x=distances,
                            y=np.sqrt(rms_values_sq),
                            visible=is_reliable_visible)]
        except CannotPerformAnalysisError as exc:
            alerts.append(make_alert_entry('warning', topography_name, topography_url, series_name, str(exc)))
        progress_offset += 1

        distances, rms_values_sq = topography.scale_dependent_statistical_property(reliable=False, **func_kwargs)
        series += [dict(name=series_name + ' (incl. unreliable data)',
                        x=distances,
                        y=np.sqrt(rms_values_sq),
                        visible=False),
                   ]
        progress_offset += 1

    x_kwargs = dict(func=lambda x, y=None: np.mean(x * x),
                    n=order_of_derivative,
                    progress_callback=progress_callback, **kwargs)

    process_series_reliable_unreliable(xname, x_kwargs, is_reliable_visible=True)

    if topography.dim == 2:
        y_kwargs = dict(func=lambda x, y=None: np.mean(x * x),
                        n=order_of_derivative,
                        progress_callback=progress_callback, **kwargs)

        process_series_reliable_unreliable(yname, y_kwargs)

        xy_kwargs = dict(func=lambda x, y: np.mean(xyfunc(x, y)),
                         n=order_of_derivative,
                         progress_callback=progress_callback, **kwargs)

        process_series_reliable_unreliable(xyname, xy_kwargs)

    unit = topography.unit
    return dict(
        name=name,
        xlabel='Distance',
        ylabel=ylabel,
        xunit=unit,
        yunit=yunit.format(unit),
        xscale='log',
        yscale='log',
        series=wrap_series(series),
        alerts=alerts)


def scale_dependent_roughness_parameter_for_surface(surface, progress_recorder, order_of_derivative, name, ylabel,
                                                    xname, yunit, storage_prefix=None, **kwargs):
    topographies = ContainerProxy(surface.topography_set.all())
    unit = suggest_length_unit(topographies, 'log')

    series = []
    alerts = []

    # Factor of two for curvature
    progress_callback = None if progress_recorder is None else lambda i, n: progress_recorder.set_progress(i + 1, n)

    try:
        distances, rms_values_sq = scale_dependent_statistical_property(
            topographies, lambda x, y=None: np.mean(x * x), n=order_of_derivative, unit=unit,
            progress_callback=progress_callback, **kwargs)
        series = [dict(name=xname,
                       x=distances,
                       y=np.sqrt(rms_values_sq),
                       )]
    except CannotPerformAnalysisError as exc:
        alerts.append(make_alert_entry('warning', surface.name, surface.get_absolute_url(), xname, str(exc)))

    return dict(
        name=name,
        xlabel='Distance',
        ylabel=ylabel,
        xunit=unit,
        yunit=yunit.format(unit),
        xscale='log',
        yscale='log',
        series=wrap_series(series),
        alerts=alerts)


@register_implementation(art=ART_SERIES, name="Scale-dependent slope")
def scale_dependent_slope(topography, progress_recorder=None, storage_prefix=None, nb_points_per_decade=10):
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
        '1',
        nb_points_per_decade=nb_points_per_decade,
        storage_prefix=storage_prefix)


@register_implementation(art=ART_SERIES, name="Scale-dependent slope")
def scale_dependent_slope_for_surface(surface, progress_recorder=None, storage_prefix=None, nb_points_per_decade=10):
    return scale_dependent_roughness_parameter_for_surface(
        surface,
        progress_recorder,
        1,
        'Scale-dependent slope',
        'Slope',
        'Slope in x-direction',
        '1',
        nb_points_per_decade=nb_points_per_decade,
        storage_prefix=storage_prefix)


@register_implementation(art=ART_SERIES, name="Scale-dependent curvature")
def scale_dependent_curvature(topography, progress_recorder=None, storage_prefix=None, nb_points_per_decade=10):
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
        '{}⁻¹',
        nb_points_per_decade=nb_points_per_decade,
        storage_prefix=storage_prefix)


@register_implementation(art=ART_SERIES, name="Scale-dependent curvature")
def scale_dependent_curvature_for_surface(surface, progress_recorder=None, storage_prefix=None,
                                          nb_points_per_decade=10):
    return scale_dependent_roughness_parameter_for_surface(
        surface,
        progress_recorder,
        2,
        'Scale-dependent curvature',
        'Curvature',
        'Curvature in x-direction',
        '{}⁻¹',
        nb_points_per_decade=nb_points_per_decade,
        storage_prefix=storage_prefix)


@register_implementation(art=ART_ROUGHNESS_PARAMETERS, name="Roughness parameters")
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


def _analysis_function(topography, funcname_profile, funcname_area, name, xlabel, ylabel, xname, yname, aname, xunit,
                       yunit, conv_2d_fac=1.0, conv_2d_exponent=0, storage_prefix=None, **kwargs):
    topography_name = topography.name
    topography_url = topography.get_absolute_url()

    # Switch to low level topography from SurfaceTopography model
    topography = topography.topography()

    if topography.is_reentrant:
        raise ReentrantTopographyException(
            '{}: Cannot calculate analysis function for reentrant measurements.'.format(name))

    alerts = []  # list of dicts with keys 'alert_class', 'message'
    series = []  # list of dicts with series data, keys: 'name', 'x', 'y', 'visible'

    func = getattr(topography, funcname_profile)

    try:
        r, A = func(**kwargs)
        # Remove NaNs
        r = r[np.isfinite(A)]
        A = A[np.isfinite(A)]

        series += [
            dict(name=xname,
                 x=r,
                 y=A,
                 ),
        ]
    except CannotPerformAnalysisError as exc:
        alerts.append(make_alert_entry('warning', topography_name, topography_url, xname, str(exc)))

    # Create dataset with unreliable data
    ru, Au = func(reliable=False, **kwargs)

    # Remove NaNs
    ru = ru[np.isfinite(Au)]
    Au = Au[np.isfinite(Au)]

    if topography.dim == 2:

        transpose_func = getattr(topography.transpose(), funcname_profile)
        areal_func = getattr(topography, funcname_area)

        try:
            r_T, A_T = transpose_func(**kwargs)
            # Remove NaNs
            r_T = r_T[np.isfinite(A_T)]
            A_T = A_T[np.isfinite(A_T)]
            series += [
                dict(name=yname,
                     x=r_T,
                     y=A_T,
                     visible=False,  # We hide everything by default except for the first data series
                     ),
            ]
        except CannotPerformAnalysisError as exc:
            alerts.append(make_alert_entry('warning', topography_name, topography_url, yname, str(exc)))

        try:
            r_2D, A_2D = areal_func(**kwargs)
            # Remove NaNs
            r_2D = r_2D[np.isfinite(A_2D)]
            A_2D = A_2D[np.isfinite(A_2D)]
            series += [
                dict(name=aname,
                     x=r_2D,
                     y=conv_2d_fac * A_2D if conv_2d_exponent == 0 else conv_2d_fac * r_2D ** conv_2d_exponent * A_2D,
                     visible=False,
                     ),
            ]
        except CannotPerformAnalysisError as exc:
            alerts.append(make_alert_entry('warning', topography_name, topography_url, aname, str(exc)))

        ru_T, Au_T = transpose_func(reliable=False, **kwargs)
        ru_2D, Au_2D = areal_func(reliable=False, **kwargs)

        # Remove NaNs
        ru_T = ru_T[np.isfinite(Au_T)]
        Au_T = Au_T[np.isfinite(Au_T)]
        ru_2D = ru_2D[np.isfinite(Au_2D)]
        Au_2D = Au_2D[np.isfinite(Au_2D)]

    #
    # Add series with unreliable data
    #
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
                 y=conv_2d_fac * Au_2D if conv_2d_exponent == 0 else conv_2d_fac * ru_2D ** conv_2d_exponent * Au_2D,
                 visible=False,
                 ),
        ]

    unit = topography.unit

    # Return metadata for results as a dictionary (to be stored in the postgres database)
    return dict(
        name=name,
        xlabel=xlabel,
        ylabel=ylabel,
        xunit=xunit.format(unit),
        yunit=yunit.format(unit),
        xscale='log',
        yscale='log',
        series=wrap_series(series),
        alerts=alerts)


def _analysis_function_for_surface(surface, progress_recorder, funcname_profile, name, xlabel, ylabel, xname, xunit,
                                   yunit, storage_prefix=None, **kwargs):
    """Calculate average analysis result for a surface."""
    topographies = ContainerProxy(surface.topography_set.all())
    unit = suggest_length_unit(topographies, 'log')

    series = []
    alerts = []

    progress_callback = None if progress_recorder is None else lambda i, n: progress_recorder.set_progress(i + 1, n)

    try:
        r, A = log_average(topographies, funcname_profile, unit, progress_callback=progress_callback, **kwargs)

        # Remove NaNs
        r = r[np.isfinite(A)]
        A = A[np.isfinite(A)]

        #
        # Build series
        #
        series += [dict(name=xname,
                        x=r,
                        y=A,
                        )]
    except CannotPerformAnalysisError as exc:
        alerts.append(make_alert_entry('warning', surface.name, surface.get_absolute_url(),
                                       xname, str(exc)))

    # Return metadata for results as a dictionary (to be stored in the postgres database)
    result = dict(
        name=name,
        xlabel=xlabel,
        ylabel=ylabel,
        xunit=xunit.format(unit),
        yunit=yunit.format(unit),
        xscale='log',
        yscale='log',
        series=wrap_series(series),
        alerts=alerts)

    return result
