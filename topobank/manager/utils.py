from django.shortcuts import reverse
from guardian.shortcuts import get_objects_for_user
from django.core.cache import cache # default cache

from PyCo.Topography import open_topography

from topobank.taskapp.celery import app


from operator import itemgetter
import logging

_log = logging.getLogger(__name__)

DEFAULT_DATASOURCE_NAME = 'Default'
UNIT_TO_METERS = {'Å': 1e-10, 'nm': 1e-9, 'µm': 1e-6, 'mm': 1e-3, 'm': 1.0,
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

def get_topography_reader(filefield):
    """Returns PyCo.Topography.IO.ReaderBase object.

    :param filefield: models.FileField instance
    :return: ReaderBase instance
    """
    # Workaround such that PyCo recognizes this a binary stream
    if not hasattr(filefield, 'mode'):
        filefield.mode = 'rb'
    return open_topography(filefield)

def mangle_unit(unit): # TODO needed?
    """
    Matplotlib does not support 'MICRO SIGN' unicode character - convert to
    'GREEK SMALL LETTER MU'.
    """
    if unit == 'µm':
        return 'μm'
    return unit

def surfaces_for_user(user, perms=['view_surface']):
    """Return a queryset of all surfaces, the user has *all* given permissions.

    :param user: user for which we want to know the surfaces
    :param perms: list of permission codenames, default is ['view_surface']
    :return: queryset of surfaces
    """
    from topobank.manager.models import Surface
    return get_objects_for_user(user, perms, klass=Surface, accept_global_perms=False)

def tags_for_user(user):
    """Return set of tags which can be used for autocompletion when editing tags.

    A user should not see all tags ever used on the app, but only those
    which were chosen by herself or collaborators.

    :param user: User instance
    :return: list of strings
    """
    surfaces = surfaces_for_user(user)

    from .models import TagModel
    from django.db.models import Q

    return TagModel.objects.filter(Q(surface__in=surfaces) | Q(topography__surface__in=surfaces)).distinct()


def selection_choices(user):
    """Compile all choices for selection topographies and surfaces for given user.

    :param user: Django user
    :return: list of choices which are 2-tuples, see documentation
    """
    surfaces = surfaces_for_user(user)

    choices = []
    for surf in surfaces:

        surf_creator = surf.creator
        group_label = "{}".format(surf.name)

        if surf_creator == user:
            group_label += " - created by you"
        else:
            group_label += " - shared by {}".format(str(surf_creator))

        surface_choices = [('surface-{}'.format(surf.id), surf.name)]
        surface_choices.extend([('topography-{}'.format(t.id), t.name)
                        for t in surf.topography_set.all().order_by('id')])

        choices.append((group_label, surface_choices)) # create subgroup

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
    return ['surface-{}'.format(s.id) for s in surfaces_for_user(user)]

def instances_to_selection(topographies=[], surfaces=[]):
    """Returns a list of strings suitable for selecting instances.

    :param topographies: sequence of Topography instances
    :param surfaces: sequence of Surface instances
    :return: list of str, alphabetically sorted
    """
    selection = []
    for topo in topographies:
        if topo.surface in surfaces:
            # will be included by surface
            continue
        selection.append(f'topography-{topo.id}')

    for surf in surfaces:
        selection.append(f'surface-{surf.id}')

    return sorted(selection)



def selection_to_instances(selection, surface=None):
    """Returns a dict with querysets of selected topographies and surfaces as saved in session.

    If surface is given, return only topographies for this
    Surface model object.

    :param selection: selection list as saved in session
    :param surface: optionally a surface to filter topographies in selection
    :return: tuple (topographies, surfaces)

    The tuple has two elements:

     'topographies': all topographies in the selection (if 'surface' is given, filtered by this surface)
     'surfaces': all surfaces explicitly found in the selection (not only because its topography was selected)

    Also surfaces without topographies are returned in 'surfaces' if selected.

    If a surface is selected, all topographies for this surface will also
    be returned.
    """
    from .models import Topography, Surface

    topography_ids = set()
    surface_ids = set()

    for type_id in selection:
        type, id = type_id.split('-')
        id = int(id)
        if type == 'topography':
            topography_ids.add(id)
        elif type == 'surface':
            surface_ids.add(id)
            if (surface is not None) and (surface.id != id):
                continue # skip this surface, it is not relevant because argument surface was given

            # either surface is None or this is the interesting surface
            # -> Also add all topographies from this surface
            topography_ids.update(list(Topography.objects.filter(surface__id=id).values_list('id', flat=True)))

    topography_ids = list(topography_ids)

    # filter for these topography ids and optionally also for surface if given one
    filter_args = dict(id__in=topography_ids)
    if surface is not None:
        filter_args['surface'] = surface
    topographies = Topography.objects.filter(**filter_args)

    surfaces = Surface.objects.filter(id__in=surface_ids)

    return (topographies, surfaces)

def selected_instances(request, surface=None):
    """Return a dict with topography and surface instances which are currently selected.

    :request: HTTP request
    :surface: if given, return only topographies of this Surface instance
    :return: tuple (topographies, surfaces)

    The tuple has two elements:

     'topographies': all topographies in the selection (if 'surface' is given, filtered by this surface)
     'surfaces': all surfaces explicitly found in the selection (not only because its topography was selected)

    Also surfaces without topographies are returned in 'surfaces' if selected.
    """
    selection = selection_from_session(request.session)
    topographies, surfaces = selection_to_instances(selection, surface=surface)

    # make sure that only topographies with read permission can be effectively selected
    topographies = [t for t in topographies
                    if request.user.has_perm('view_surface', t.surface)]
    surfaces = [s for s in surfaces
                if request.user.has_perm('view_surface', s)]

    return topographies, surfaces

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

        try:
            unit = pyco_topo.info['unit']
        except KeyError:
            unit = None

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
