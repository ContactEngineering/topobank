
import numpy as np

from PyCo.Topography import FromFile
from PyCo.Topography.TopographyDescription import ScaledTopography, DetrendedTopography

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



