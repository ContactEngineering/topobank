from django.shortcuts import reverse
from django.conf import settings
from matplotlib import pyplot as plt
import io
import os
import pathlib

from PyCo.Topography import FromFile
from PyCo.Topography.TopographyDescription import ScaledTopography, DetrendedTopography
from deepzoom import ImageCreator

from topobank.taskapp.celery import app

import numpy as np
import logging

_log = logging.getLogger(__name__)

DEFAULT_DATASOURCE_NAME = 'Default'
UNIT_TO_METERS = {'A': 1e-10, 'nm': 1e-9, 'µm': 1e-6, 'mm': 1e-3, 'm': 1.0,
                  'unknown': 1.0}

SELECTION_SESSION_VARNAME = 'selection'

class TopographyFile:
    """Provide a simple generic interface to topography files independent of format."""

    def __init__(self, fname):

        self._fmt = FromFile.detect_format(fname)
        raw_surfaces = FromFile.read(fname, self._fmt)
        # we are relying here on a fixed order everytime the same file is read

        #
        # read() may return only one surface if there is only one
        #
        if not isinstance(raw_surfaces, list):
            raw_surfaces = [raw_surfaces]

        surfaces = [] # filtered surfaces
        # ignore all surfaces which have other units than lenghts
        # code taken from PyCo-web
        for surface in raw_surfaces:
            if type(surface.unit) is not tuple:
                # If this is not a tuple, that x-, y- and z-units are all
                # lengths. Discard all other channels.
                if not isinstance(surface, ScaledTopography):
                    surface = ScaledTopography(surface, 1.0)
                surfaces += [DetrendedTopography(surface, detrend_mode='height')]
        self._surfaces = surfaces


    @property
    def data_sources(self):
        """Return list of data source strings from surface infos."""
        return [ s.info['data_source'] if 'data_source' in s.info else DEFAULT_DATASOURCE_NAME
                 for s in self._surfaces ]

    def topography(self, data_source):
        """Get ScaledTopography instance based on data_source.

        :param data_source: integer
        :return: PyCo.Surface.SurfaceDescription.ScaledSurface
        """

        return self._surfaces[data_source] # TODO adjust to new PyCo naming


def optimal_unit(length, unit='m'): # TODO write unit tests
    """
    Return a unit and a scale factor that minimizes the display width of a
    length.
    """
    if unit is None:
        return 'unknown', 1
    unit_fac = UNIT_TO_METERS[unit]
    if unit_fac is None:
        return unit, 1

    # Convert length to meters
    length = np.mean(length)*unit_fac # TODO why mean here? Test missing.

    # Length is meters now
    new_unit = 'm'
    conversion_factor = unit_fac / UNIT_TO_METERS['m']
    for name, meters in sorted(UNIT_TO_METERS.items(), key=lambda x: x[1]):
        if meters is not None and length > 1.1*meters:
            new_unit = name
            conversion_factor = unit_fac/meters

    return new_unit, conversion_factor

def mangle_unit(unit): # TODO needed?
    """
    Matplotlib does not support 'MICRO SIGN' unicode character - convert to
    'GREEK SMALL LETTER MU'.
    """
    if unit == 'µm':
        return 'μm'
    return unit

# def selected_topographies(request, surface=None):
#     """Returns selected topographies as saved in session.
#
#     If surface is given, return only topographies for this
#     Surface model object
#     """
#     from .models import Topography
#     topography_ids = request.session.get('selected_topographies', [])
#
#     filter_args = dict(surface__user=request.user, id__in=topography_ids)
#     if surface is not None:
#         filter_args['surface']=surface
#     topographies = Topography.objects.filter(**filter_args)
#
#     return topographies


def selection_choices(user):
    """Compile all choices for selection topographies and surfaces.

    :param user: Django user
    :return: list of choices which are 2-tuples, see documentation
    """
    from topobank.manager.models import Surface

    surfaces = Surface.objects.filter(user=user)

    choices = []
    for s in surfaces:
        choices.append(('surface-{}'.format(s.id), s.name))
        choices.extend([('topography-{}'.format(t.id), t.name) for t in s.topography_set.all().order_by('id')])

    return choices

def selection_from_session(session):
    """Get selection from session.

    The selection is a list of strings like

    [ 'topography-1', 'surface-4']

    which represents the selected objects.
    """
    return session.get(SELECTION_SESSION_VARNAME, [])

def selection_for_select_all(user):
    """Return selection if given user wants to select all topographies and surfaces.

    :param user: Django user
    :return:
    """
    from .models import Surface
    return ['surface-{}'.format(s.id)
            for s in Surface.objects.filter(user=user)]

def selection_to_topographies(selection, user, surface=None):  # TODO rename to "selected_topographies"
    """Returns selected topographies from current user as saved in session.

    If surface is given, return only topographies for this
    Surface model object.

    TODO make more efficicient if only topographies for a single surface needed
    """
    from .models import Topography

    topography_ids = set()

    for type_id in selection:
        type, id = type_id.split('-')
        id = int(id)
        if type == 'topography':
            topography_ids.add(id)
        elif type == 'surface':
            if (surface is not None) and (surface.id != id):
                continue # skip this surface, it is not relevant

            topography_ids.update(list(Topography.objects.filter(surface__id=id).values_list('id', flat=True)))

    topography_ids = list(topography_ids)

    # filter for user and optionally also for a single surface
    filter_args = dict(surface__user=user, id__in=topography_ids)
    if surface is not None:
        filter_args['surface'] = surface # todo needed?
    topographies = Topography.objects.filter(**filter_args)

    return topographies

def selected_topographies(request, surface=None):
    """Return list of topography instances which are currently selected.

    :request: HTTP request
    :surface: if given, return only topographies of this Surface instance
    """
    return selection_to_topographies(selection_from_session(request.session), request.user, surface=surface)

def bandwidths_data(topographies):
    """Return bandwidths data as needed in surface summary plots.

    :param topographies: iterable with manager.models.Topography instances
    :return: list of dicts with bandwidths data

    Each list element is a dict with keys

    'upper_bound': upper bound in meters
    'lower_bound': lower bound in meters
    'name': name of topography
    'link': link to topography details
    """
    bandwidths_data = []

    for topo in topographies:

        pyco_topo = topo.topography()

        unit = pyco_topo.unit
        if unit is None:
            _log.warning("No unit given for topography {}. Cannot display bandwidth.".format(topo.name))
            continue
        elif not unit in UNIT_TO_METERS:
            _log.warning("Unknown unit {} given for topography {}. Cannot display bandwidth.".format(
                unit, topo.name))
            continue

        meter_factor = UNIT_TO_METERS[unit]

        lower_bound_meters = np.mean(pyco_topo.pixel_size) * meter_factor
        upper_bound_meters = np.mean(pyco_topo.size) * meter_factor

        bandwidths_data.append(
            {
                'lower_bound': lower_bound_meters,
                'upper_bound': upper_bound_meters,
                'name': topo.name,
                'link': reverse('manager:topography-detail', kwargs=dict(pk=topo.pk))
            }
        )

    return bandwidths_data

@app.task(bind=True, ignore_result=True)
def create_topography_images(self, topography_id):
    """Create image for surface for web interface.

    :param topography_id: id of Topography instance
    :return: None

    The topography instance will be changed.
    """

    from topobank.manager.models import Topography

    #
    # Get data needed for the image
    #
    _log.info("topography_id: %d", topography_id)
    topography = Topography.objects.get(id=topography_id)
    _log.info("Topography: %s", topography)
    pyco_topo = topography.topography()

    arr = pyco_topo.array()

    #
    # Prepare figure
    #
    DPI = 30 # TODO check value
    topo_size = pyco_topo.size
    figsize = (topo_size[0]/DPI, topo_size[1]/DPI)
    fig = plt.figure(figsize=figsize)
    ax = fig.add_subplot(1, 1, 1)
    ax.pcolormesh(arr)

    #
    # save figure in a memory buffer and use this as source for image field
    #
    buffer = io.BytesIO()
    fig.savefig(buffer, format='jpeg')

    img_path = pathlib.Path(topography.surface.user.get_media_path()) / 'images' / f'topography-{topography.pk}.jpeg'

    _log.info(f"Saving topography image as '{img_path}'...")
    topography.image.save(img_path, buffer, save=True)

    #
    # create the dzi images for zooming + XML file with extension .dzi
    #
    _log.info("Creating DZI image of topography for zooming...")
    dzi_path = img_path.with_suffix('.dzi')
    image_creator = ImageCreator()
    image_creator.create(img_path, os.fspath(dzi_path)) # last argument needs a str path

    #
    # saving reference in topography instance relative to MEDIA_ROOT, will be used to generate URL
    #
    topography.dzi_file = os.fspath(dzi_path.relative_to(settings.MEDIA_ROOT))
    topography.save()

    _log.info("Done creating images for topography id {}.".format(topography_id))

