import io
import json
import tempfile

import numpy as np
import xarray as xr
from ContactMechanics import PeriodicFFTElasticHalfSpace, FreeFFTElasticHalfSpace, make_system
from ContactMechanics.Factory import make_plastic_system
from ContactMechanics.Tools.ContactAreaAnalysis import patch_areas
from SurfaceTopography import PlasticTopography
from SurfaceTopography.Support.UnitConversion import get_unit_conversion_factor, suggest_length_unit_for_data
from _SurfaceTopography import assign_patch_numbers
from bokeh.core.json_encoder import BokehJSONEncoder
from django.conf import settings
from django.core.files import File

from topobank.analysis.functions import _log, IncompatibleTopographyException
from topobank.analysis.registry import register_implementation
from topobank.manager.utils import default_storage_replace, make_dzi

ART_CONTACT_MECHANICS = "contact mechanics"

CONTACT_MECHANICS_MAX_MB_GRID_PTS_PRODUCT = 100000000
CONTACT_MECHANICS_MAX_MB_GRID_PTS_PER_DIM = 10000


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

    # Get topography object from contact system
    topography = system.surface

    try:
        # Reset plastic displacement if this is a plastic calculation. We need to do this because the individual steps
        # are not in order, i.e. the contact is not continuously formed or lifted. Each calculation needs to compute
        # a fresh plastic displacement.
        topography.plastic_displ = np.zeros_like(topography.plastic_displ)
    except AttributeError:
        pass

    # Get substrate object from contact system
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

    # Get topography object from contact system
    topography = system.surface

    try:
        # Reset plastic displacement if this is a plastic calculation. We need to do this because the individual steps
        # are not in order, i.e. the contact is not continuously formed or lifted. Each calculation needs to compute
        # a fresh plastic displacement.
        topography.plastic_displ = np.zeros_like(topography.plastic_displ)
    except AttributeError:
        pass

    # Get substrate object from contact system
    substrate = system.substrate

    # Get the profile as a numpy array
    heights = topography.heights()

    # Find max, min and mean heights
    middle = np.mean(heights)

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


@register_implementation(art=ART_CONTACT_MECHANICS, name="Contact mechanics")
def contact_mechanics(topography, substrate_str="nonperiodic", hardness=None, nsteps=10,
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

    The default argument of `substrate_str` was changed to `"nonperiodic"` because of problems
    when requesting the results, when using `None`. See GH issue #788.
    """
    # Check whether function is called with the right substrate_str and issue a warning if not
    alerts = []  # list of dicts with keys 'alert_class', 'message'
    if topography.is_periodic != (substrate_str == 'periodic'):
        alert_link = f'<a class="alert-link" href="{topography.get_absolute_url()}">{topography.name}</a>'
        alert_message = f"Measurement {alert_link} is "
        if topography.is_periodic:
            alert_message += "periodic, but the analysis is configured for free boundaries."
        else:
            alert_message += "not periodic, but the analysis is configured for periodic boundaries."
        alerts.append(dict(alert_class=f"alert-warning", message=alert_message))
        _log.warning(alert_message + " The user should have been informed in the UI.")

    # Get low level topography from SurfaceTopography model
    topography = topography.topography()

    if topography.dim == 1:
        raise IncompatibleTopographyException("Contact mechanics not implemented for line scans.")

    # Limit size of topographies for which this calculation is possible
    nb_grid_pts_x, nb_grid_pts_y = topography.nb_grid_pts
    if nb_grid_pts_x * nb_grid_pts_y > CONTACT_MECHANICS_MAX_MB_GRID_PTS_PRODUCT:
        raise IncompatibleTopographyException(f"Topography has ({nb_grid_pts_x}, {nb_grid_pts_y}) points, "
                                              f"which are more than {CONTACT_MECHANICS_MAX_MB_GRID_PTS_PRODUCT} - "
                                              "this is currently too large for a Contact mechanics calculation.")
    if max(nb_grid_pts_x, nb_grid_pts_y) > CONTACT_MECHANICS_MAX_MB_GRID_PTS_PER_DIM:
        raise IncompatibleTopographyException(f"Topography has ({nb_grid_pts_x}, {nb_grid_pts_y}) points, "
                                              f"so more than {CONTACT_MECHANICS_MAX_MB_GRID_PTS_PER_DIM} points "
                                              "in one direction - this is currently too large for a "
                                              "Contact mechanics calculation.")

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

    if (hardness is not None) and (hardness > 0):
        system = make_plastic_system(substrate, topography)
    else:
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
        # Save displacement_xy, gap_xy, pressure_xy and contacting_points_xy to a NetCDF file
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

        storage_path = f'{storage_prefix}/step-{i}'
        data_paths.append(storage_path)
        with tempfile.NamedTemporaryFile(prefix='analysis-') as tmpfile:
            dataset.to_netcdf(tmpfile.name, format=netcdf_format)
            tmpfile.seek(0)
            default_storage_replace(f'{storage_path}/nc/results.nc', File(tmpfile))

        #
        # Pressure and gap distribution
        #

        fac = get_unit_conversion_factor(topography.unit, 'm')

        hist, edges = np.histogram(pressure_xy, density=True, bins=50)
        data_dict = {
            'pressure': (edges[1:-1] + edges[2:]) / 2,
            'pressureProbabilityDensity': hist[1:],
            'pressureLabel': 'Pressure p',
            'pressureUnit': 'E*',
            'pressureProbabilityDensityLabel': 'Probability density P(p)',
            'pressureProbabilityDensityUnit': 'E*⁻¹'
        }

        hist, edges = np.histogram(gap_xy, density=True, bins=50)
        data_dict.update({
            'gap': (edges[1:-1] + edges[2:]) / 2,
            'gapProbabilityDensity': hist[1:],
            'gapLabel': 'Gap g',
            'gapUnit': topography.unit,
            'gapSIScaleFactor': fac,
            'gapProbabilityDensityLabel': 'Probability density P(p)',
            'gapProbabilityDensityUnit': f'{topography.unit}⁻¹',
            'gapProbabilityDensitySIScaleFactor': 1 / fac
        })

        #
        # Patch size distribution
        #

        patch_ids = assign_patch_numbers(contacting_points_xy, substrate_str == 'periodic')[1]
        cluster_areas = patch_areas(patch_ids) * substrate.area_per_pt
        hist, edges = np.histogram(cluster_areas, density=True, bins=50)
        data_dict.update({
            'clusterArea': (edges[1:-1] + edges[2:]) / 2,
            'clusterAreaProbabilityDensity': hist[1:],
            'clusterAreaLabel': 'Cluster area A',
            'clusterAreaUnit': f'{topography.unit}²',
            'clusterAreaSIScaleFactor': fac * fac,
            'clusterAreaProbabilityDensityLabel': 'Probability density P(A)',
            'clusterAreaProbabilityDensityUnit': f'{topography.unit}⁻²',
            'clusterAreaProbabilityDensitySIScaleFactor': 1 / (fac * fac)
        })

        #
        # Write to storage
        #
        default_storage_replace(f'{storage_path}/json/distributions.json',
                                io.BytesIO(json.dumps(data_dict, cls=BokehJSONEncoder).encode('utf-8')))

        #
        # Make Deep Zoom Images of pressure, contacting points, gap and displacement
        #

        make_dzi(pressure_xy.data, f'{storage_path}/dzi/pressure',
                 physical_sizes=topography.physical_sizes, unit=topography.unit,
                 colorbar_title='Pressure (E*)')
        make_dzi(contacting_points_xy.data.astype(np.int), f'{storage_path}/dzi/contacting-points',
                 physical_sizes=topography.physical_sizes, unit=topography.unit, cmap='magma')

        unit = suggest_length_unit_for_data('linear', gap_xy.data, topography.unit)
        make_dzi(gap_xy.data * get_unit_conversion_factor(topography.unit, unit), f'{storage_path}/dzi/gap',
                 physical_sizes=topography.to_unit(unit).physical_sizes, unit=unit,
                 colorbar_title=f'Gap ({unit})')

        unit = suggest_length_unit_for_data('linear', displacement_xy.data, topography.unit)
        make_dzi(displacement_xy.data * get_unit_conversion_factor(topography.unit, unit),
                 f'{storage_path}/dzi/displacement',
                 physical_sizes=topography.to_unit(unit).physical_sizes, unit=unit,
                 colorbar_title=f'Displacement ({unit})')

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
        ),
        alerts=alerts,
    )
