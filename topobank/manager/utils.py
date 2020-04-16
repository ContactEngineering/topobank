from django.shortcuts import reverse
from guardian.shortcuts import get_objects_for_user
from django.conf import settings
import markdown2

from PyCo.Topography import open_topography
from PyCo.Topography.IO import readers as pyco_readers

import traceback
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


def get_reader_infos():
    reader_infos = []
    for reader_class in pyco_readers:
        try:
            # some reader classes have no description yet
            descr = reader_class.description()
        except Exception:
            descr = "*description not yet available*"

        descr = markdown2.markdown(descr)

        reader_infos.append((reader_class.name(), reader_class.format(), descr))

    return reader_infos

def get_topography_reader(filefield, format=None):
    """Returns PyCo.Topography.IO.ReaderBase object.

    Parameters
    ----------

    filefield: models.FileField instance
        reference to file which should be opened by the reader
    format: str, optional
        specify in which format the file should be interpreted;
        if not given, the format is determined automatically

    Returns
    -------
        Instance of a `ReaderBase` subclass according to the format.
    """
    # Workaround such that PyCo recognizes this a binary stream
    if not hasattr(filefield, 'mode'):
        filefield.mode = 'rb'
    if hasattr(filefield.file, 'seek'):
        # make sure the file is rewinded
        filefield.file.seek(0)
    return open_topography(filefield, format=format)


def surfaces_for_user(user, perms=['view_surface']):
    """Return a queryset of all surfaces, the user has *all* given permissions.

    :param user: user for which we want to know the surfaces
    :param perms: list of permission codenames, default is ['view_surface']
    :return: queryset of surfaces
    """
    from topobank.manager.models import Surface
    return get_objects_for_user(user, perms, klass=Surface, accept_global_perms=False)

def tags_for_user(user, surfaces=None):
    """Return set of tags which can be used for autocompletion when editing tags.

    A user should not see all tags ever used on the app, but only those
    which were chosen by herself or collaborators and corresponding parent tags.

    :param user: User instance
    :param surfaces: surfaces for user, if None, will be computed; specify this to reuse previous calculation
    :return: list of strings
    """
    if surfaces is None:
        surfaces = surfaces_for_user(user)

    from .models import TagModel
    from django.db.models import Q

    tags = TagModel.objects.filter(Q(surface__in=surfaces) | Q(topography__surface__in=surfaces))

    # add parent tags not already included
    for t in tags:
        tags |= t.get_ancestors()

    return tags.distinct()

def selection_from_session(session):
    """Get selection from session.

    The selection is a list of strings like

    [ 'topography-1', 'surface-4']

    which represents the selected objects.
    """
    return session.get(SELECTION_SESSION_VARNAME, [])


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
    """Returns a tuple with querysets of selected topographies, surfaces, and tags as saved in session.

    If surface is given, return only topographies for this
    Surface model object.

    :param selection: selection list as saved in session
    :param surface: optionally a surface to filter topographies in selection
    :return: tuple (topographies, surfaces)

    The returned tuple has 3 elements:

     'topographies': all topographies in the selection (if 'surface' is given, filtered by this surface)
     'surfaces': all surfaces explicitly found in the selection (not only because its topography was selected)
     'tags': all tags explicitly found in the selection

    Also surfaces without topographies are returned in 'surfaces' if selected.

    If a surface is selected, all topographies for this surface will also
    be returned.
    """
    from .models import Topography, Surface, TagModel

    topography_ids = set()
    surface_ids = set()
    tag_ids = set()

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
        elif type == 'tag':
            tag_ids.add(id)

    topography_ids = list(topography_ids)

    # filter for these topography ids and optionally also for surface if given one
    filter_args = dict(id__in=topography_ids)
    if surface is not None:
        filter_args['surface'] = surface
    topographies = Topography.objects.filter(**filter_args)

    surfaces = Surface.objects.filter(id__in=surface_ids)
    tags = TagModel.objects.filter(id__in=tag_ids)

    return (topographies, surfaces, tags)

def selected_instances(request, surface=None):  # TODO check whether 'surface' argument is still needed
    """Return a tuple with topography, surface, and tag instances which are currently selected.

    :request: HTTP request
    :surface: if given, return only topographies of this Surface instance
    :return: tuple (topographies, surfaces, tags)

    The returned tuple has 3 elements, each a list:

     'topographies': all topographies in the selection (if 'surface' is given, filtered by this surface)
     'surfaces': all surfaces explicitly found in the selection (not only because its topography was selected)
     'tags': all tags explicitly found in selection

    Also surfaces without topographies are returned in 'surfaces' if selected.

    If only one topography is selected, it's surface is *not* returned in 'surfaces'.
    If a surface is explicitly selected, all of its topographies are contained in 'topographies'.
    """
    selection = selection_from_session(request.session)
    topographies, surfaces, tags = selection_to_instances(selection, surface=surface)

    # make sure that only topographies with read permission can be found here
    topographies = [t for t in topographies
                    if request.user.has_perm('view_surface', t.surface)]
    surfaces = [s for s in surfaces
                if request.user.has_perm('view_surface', s)]

    return topographies, surfaces, list(tags)

def current_selection_as_basket_items(request):
    """Returns current selection as JSON suitable for the basket.

    Parameters
    ----------
    request

    Returns
    -------
    List of items in the basket. Each is a dict with keys

     name, type, unselect_url, key

    Example with one selected surface:

     [ {'name': "Test Surface",
        'type': "surface",
        'unselect_url': ".../manager/surface/13/unselect",
        'key': "surface-13"}
     ]

    """
    topographies, surfaces, tags = selected_instances(request)

    basket_items = []
    for s in surfaces:
        unselect_url = reverse('manager:surface-unselect', kwargs=dict(pk=s.pk))
        basket_items.append(dict(name=s.name,
                                 type="surface",
                                 unselect_url=unselect_url,
                                 key=f"surface-{s.pk}"))
    for topo in topographies:
        unselect_url = reverse('manager:topography-unselect', kwargs=dict(pk=topo.pk))
        basket_items.append(dict(name=topo.name,
                                 type="topography",
                                 unselect_url=unselect_url,
                                 key=f"topography-{topo.pk}",
                                 surface_key=f"surface-{topo.surface.pk}"))
    for tag in tags:
        unselect_url = reverse('manager:tag-unselect', kwargs=dict(pk=tag.pk))
        basket_items.append(dict(name=tag.name,
                                 type="tag",
                                 unselect_url=unselect_url,
                                 key=f"tag-{tag.pk}"))

    return basket_items


def mailto_link_for_reporting_an_error(subject, info, err_msg, traceback) -> str:
    """Use this to create a mail body for reporting an error.

    :param subject: mail subject (str)
    :param info: some text about the context, where the error happened (str)
    :param err_msg: error message (str)
    :param traceback: as reported by traceback.format_exc() (str)
    :return: a string which can be used in a mailto link for the mail body
    """
    body = body_for_mailto_link_for_reporting_an_error(info, err_msg, traceback)
    return f"mailto:{settings.CONTACT_EMAIL_ADDRESS}?subject={subject}&body={body}"


def body_for_mailto_link_for_reporting_an_error(info, err_msg, traceback) -> str:
    """Use this to create a mail body for reporting an error.

    :param info: some text about the context, where the error happened
    :param err_msg: error message
    :param traceback: as reported by traceback.format_exc()
    :return: a string which can be used in a mailto link for the mail body
    """

    body = ("Hey there,\n\n"
            "I've problems with 'contact.engineering'.\n\nHere are some details:\n\n"
            f"Context: {info}\n"
            f"Error message: {err_msg}\n")

    body += "Traceback:\n"

    body += "-"*72+"\n"
    body += f"\n{traceback}\n"
    body += "-"*72+"\n"
    body += "\n\nBest, <your name>"

    # change characters to we can use this in a link
    body = body.replace('\n', '%0D%0A')
    return body



def _bandwidths_data_entry(topo):
    """Return an entry for bandwiths_data

    :param topo: topobank.manager.models.Topography instance
    :return: dict
    """

    err_message = None

    try:
        pyco_topo = topo.topography()
    except Exception:
        err_message = "Topography '{}' (id: {}) cannot be loaded unexpectedly.".format(
            topo.name, topo.id)
        _log.error(err_message+"\n"+traceback.format_exc())

        link = mailto_link_for_reporting_an_error(f"Failure loading topography (id: {topo.id})",
                                                  "Bandwidth data calculation",
                                                  err_message,
                                                  traceback.format_exc())

        return {
                'lower_bound': None,
                'upper_bound': None,
                'name': topo.name,
                'link': link,
                'error_message': err_message
        }

    try:
        unit = pyco_topo.info['unit']
    except KeyError:
        unit = None

    if unit is None:
        _log.warning("No unit given for topography {}. Cannot calculate bandwidth.".format(topo.name))
        err_message = 'No unit given for topography, cannot calculate bandwidth.'
    elif not unit in UNIT_TO_METERS:
        _log.warning("Unknown unit {} given for topography {}. Cannot calculate bandwidth.".format(
            unit, topo.name))
        err_message = "Unknown unit {} given for topography {}. Cannot calculate bandwidth.".format(
            unit, topo.name)

    meter_factor = UNIT_TO_METERS[unit]

    if err_message is None:

        lower_bound, upper_bound = pyco_topo.bandwidth()
        # Workaround for https://github.com/pastewka/PyCo/issues/55
        if isinstance(upper_bound, tuple):
            upper_bound = upper_bound[0]

        lower_bound_meters = lower_bound * meter_factor
        upper_bound_meters = upper_bound * meter_factor

    else:
        lower_bound_meters = None
        upper_bound_meters = None

    return {
            'lower_bound': lower_bound_meters,
            'upper_bound': upper_bound_meters,
            'name': topo.name,
            'link': reverse('manager:topography-detail', kwargs=dict(pk=topo.pk)),
            'error_message': err_message
    }



def bandwidths_data(topographies):
    """Return bandwidths data as needed in surface summary plots.

    :param topographies: iterable with manager.models.Topography instances
    :return: list of dicts with bandwidths data

    Each list element is a dict with keys

    'upper_bound': upper bound in meters (or None if there is an error)
    'lower_bound': lower bound in meters (or None if there is an error)
    'name': name of topography
    'link': link to topography details
    'error_message': None or a string with an error message if calculation failed

    The list is sorted by the lower bound with larger lower bound first.

    The idea is to be able to display error messages and the links
    also on javascript level which gets this data.
    """
    bandwidths_data = [ _bandwidths_data_entry(t) for t in topographies]

    #
    # Sort by lower bound, put lower bound=None first to show error messages first in plot
    #
    def weight(entry):
        lb = entry['lower_bound']
        return float('inf') if lb is None else lb

    bandwidths_data.sort(key=lambda entry: weight(entry), reverse=True)

    return bandwidths_data
