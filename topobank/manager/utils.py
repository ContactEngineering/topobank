from django.shortcuts import reverse
from django.core.cache import cache # default cache

from PyCo.Topography import FromFile

from topobank.taskapp.celery import app

import os.path
import numpy as np
from operator import itemgetter
import logging

_log = logging.getLogger(__name__)

DEFAULT_DATASOURCE_NAME = 'Default'
UNIT_TO_METERS = {'A': 1e-10, 'nm': 1e-9, 'µm': 1e-6, 'mm': 1e-3, 'm': 1.0,
                  'unknown': 1.0}

SELECTION_SESSION_VARNAME = 'selection'

class TopographyFileException(Exception):
    pass

class TopographyFileFormatException(TopographyFileException):
    pass

class TopographyFileReadingException(TopographyFileException):

    def __init__(self, fname, detected_format, message):
        self._fname = fname
        self._detected_format = detected_format
        self._message = message

    def __str__(self):
        return "Error loading file '{}' (assuming format '{}'): {}".format(
            self._fname, self._detected_format, self._message
        )

    @property
    def detected_format(self):
        return self._detected_format

    @property
    def message(self):
        return self._message

def get_topography_file(datafile_fname): # TODO check, maybe also use user to make unique
    """Create topography file instance or get it from cache.

    :param datafile_fname: local filename
    :return: TopographyFile instance
    """
    cache_key = datafile_fname
    topofile = cache.get(cache_key)
    if topofile is None:
        topofile = TopographyFile(datafile_fname)
        cache.set(cache_key, topofile)
    return topofile

class TopographyFile:
    """Provide a simple generic interface to topography files independent of format."""

    def __init__(self, fname):
        """
        :param fname: filename of topography file
        :raises: TopographyFileReadingException
        """
        try:
            self._fmt = FromFile.detect_format(fname)
        except Exception as exc:
            raise TopographyFileFormatException("Cannot detect file format. Details: "+str(exc)) from exc

        if hasattr(fname, 'seek'):
            fname.seek(0)

        try:
            raw_topographies = FromFile.read(fname, format=self._fmt)
            # we are relying here on a fixed order of data sources
            # every time the same file is read (TODO: is that ensured in PyCo?)
        except Exception as exc:
            raise TopographyFileReadingException(fname, self._fmt, str(exc)) from exc

        #
        # read() may return only one topography if there is only one
        #
        if not isinstance(raw_topographies, list):
            raw_topographies = [raw_topographies]

        topographies = [] # filtered topographies
        # ignore all topographies which have other units than lenghts
        # code taken from PyCo-web
        for topography in raw_topographies:
            #
            # ignore all data sources which have tuples as unit
            #
            try:
                unit = topography.info['unit']
            except KeyError:
                unit = None

            if not isinstance(unit, tuple):
                topographies.append(topography) # scale + detrend is done later, see Topography.topography()

        self._topographies = topographies


    @property
    def data_sources(self):
        """Return list of data source strings from topography infos."""
        return [s.info['data_source'] if 'data_source' in s.info else DEFAULT_DATASOURCE_NAME
                for s in self._topographies]

    def topography(self, data_source):
        """Get topography/line scan instance from data_source.

        The result is the unmodified topography as returned from PyCo's read function.

        :param data_source: integer
        :return: TODO specify data type
        """

        return self._topographies[data_source]


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

    The list is sorted by the lower bound with larger lower bound first.
    """
    bandwidths_data = []

    for topo in topographies:

        pyco_topo = topo.topography()

        unit = pyco_topo.info['unit']
        if unit is None:
            _log.warning("No unit given for topography {}. Cannot calculate bandwidth.".format(topo.name))
            continue
        elif not unit in UNIT_TO_METERS:
            _log.warning("Unknown unit {} given for topography {}. Cannot calculate bandwidth.".format(
                unit, topo.name))
            continue

        meter_factor = UNIT_TO_METERS[unit]

        lower_bound, upper_bound = pyco_topo.bandwidth()
        # Workaround for https://github.com/pastewka/PyCo/issues/55
        if isinstance(upper_bound, tuple):
            upper_bound = upper_bound[0]

        lower_bound_meters = lower_bound * meter_factor
        upper_bound_meters = upper_bound * meter_factor

        bandwidths_data.append(
            {
                'lower_bound': lower_bound_meters,
                'upper_bound': upper_bound_meters,
                'name': topo.name,
                'link': reverse('manager:topography-detail', kwargs=dict(pk=topo.pk))
            }
        )

    # Finally sort by lower bound
    bandwidths_data.sort(key=itemgetter('lower_bound'), reverse=True)

    return bandwidths_data
