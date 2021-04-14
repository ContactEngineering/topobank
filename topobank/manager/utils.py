from django.shortcuts import reverse
from guardian.shortcuts import get_objects_for_user
from django.conf import settings
from django.db.models import Q
from django.core.exceptions import PermissionDenied
from django.contrib.contenttypes.models import ContentType
import markdown2
from os.path import devnull
import traceback
import logging
import json

from selenium import webdriver
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.firefox.firefox_binary import FirefoxBinary

from SurfaceTopography import open_topography
from SurfaceTopography.IO import readers as surface_topography_readers


_log = logging.getLogger(__name__)

DEFAULT_DATASOURCE_NAME = 'Default'
UNIT_TO_METERS = {'Å': 1e-10, 'nm': 1e-9, 'µm': 1e-6, 'mm': 1e-3, 'm': 1.0, 'km': 1000.0,
                  'unknown': 1.0}
MAX_LEN_SEARCH_TERM = 200
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
    for reader_class in surface_topography_readers:
        # noinspection PyBroadException
        try:
            # some reader classes have no description yet
            descr = reader_class.description()
        except Exception:
            descr = "*description not yet available*"

        descr = markdown2.markdown(descr, extras=['fenced-code-blocks'])

        reader_infos.append((reader_class.name(), reader_class.format(), descr))

    return reader_infos


def get_topography_reader(filefield, format=None):
    """Returns SurfaceTopography.IO.ReaderBase object.

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
    # Workaround such that SurfaceTopography module recognizes this a binary stream
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


def filtered_surfaces(request):
    """

    Parameters
    ----------
    request
        Request instance

    Returns
    -------
        Filtered queryset of surfaces
    """

    user = request.user
    # start with all surfaces which are visible for the user
    qs = surfaces_for_user(user)

    #
    # Filter by category and sharing status
    #
    category = get_category(request)
    if category != 'all':
        qs = qs.filter(category=category)

    sharing_status = get_sharing_status(request)
    if sharing_status == 'own':
        qs = qs.filter(creator=user)
    elif sharing_status == 'shared':
        qs = qs.filter(~Q(creator=user)).exclude(publication__isnull=False)  # exclude published and own surfaces
    elif sharing_status == 'published':
        qs = qs.exclude(publication__isnull=True)

    #
    # Filter by search term
    #
    search_term = get_search_term(request)
    if search_term:
        #
        # find all topographies which should be at top level
        #
        qs = qs.filter(Q(name__icontains=search_term) |
                       Q(description__icontains=search_term) |
                       Q(tags__name__icontains=search_term) |
                       Q(topography__name__icontains=search_term) |
                       Q(topography__description__icontains=search_term) |
                       Q(topography__tags__name__icontains=search_term)).distinct()
    return qs


def filtered_topographies(request, surfaces):
    """Return topographies which match a request.

    Parameters
    ----------
    request
    surfaces
        queryset with surfaces which already match

    Returns
    -------
    queryset with matching topographies

    """
    from topobank.manager.models import Topography
    topographies = Topography.objects.filter(surface__in=surfaces)
    search_term = get_search_term(request)
    if search_term:
        topographies = topographies.filter(
                Q(name__icontains=search_term) |
                Q(description__icontains=search_term) |
                Q(tags__name__icontains=search_term))
    return topographies.distinct()


def tags_for_user(user, surfaces=None, topographies=None):
    """Return set of tags which can be used for autocomplete when editing tags.

    A user should not see all tags ever used on the app, but only those
    which were chosen by herself or collaborators and corresponding parent tags.

    :param user: User instance
    :param surfaces: surfaces to use, if None,
                     will be computed for given user; specify this to reuse previous calculation
                     or to reduce number of surfaces based on a request
    :param topographies: topographies to use, if None,
                     will be computed from surfaces; specify this to reuse previous calculation
                     or to reduce number of topographies based on a request
    :return: list of strings
    """
    from .models import TagModel, Topography
    from django.db.models import Q

    if surfaces is None:
        surfaces = surfaces_for_user(user)
    if topographies is None:
        topographies = Topography.objects.filter(surface__in=surfaces)

    tags = TagModel.objects.filter(Q(surface__in=surfaces) | Q(topography__in=topographies))

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


def instances_to_topographies(topographies, surfaces, tags):
    """Returns a queryset of topographies, based on given instances

    Given topographies, surfaces and tags are resolved and
    all topographies are returned which are either
    - explicitly given
    - given indirectly by a surface
    - given indirectly by a tag, if the topography is tagged accordingly
    - given indirectly by a tag, if its surface is tagged accordingly

    Parameters
    ----------
    topographies: sequence of topographies
    surfaces: sequence of surfaces
    tags: sequence of tags

    Returns
    -------
    Queryset of topography, distinct
    """
    from .models import Topography

    topography_ids = [topo.id for topo in topographies]
    surface_ids = [s.id for s in surfaces]
    tag_ids = [tag.id for tag in tags]

    topographies = Topography.objects.filter(id__in=topography_ids)
    topographies |= Topography.objects.filter(surface__in=surface_ids)
    topographies |= Topography.objects.filter(surface__tags__in=tag_ids)
    topographies |= Topography.objects.filter(tags__in=tag_ids)

    return topographies.distinct().order_by('id')


def instances_to_surfaces(surfaces, tags):
    """Returns a queryset of surfaces, based on given instances

    Given surfaces and tags are resolved and
    all surfaces are returned which are either
    - explicitly given
    - given indirectly by a tag, if the surface is tagged accordingly

    Parameters
    ----------
    surfaces: sequence of surfaces
    tags: sequence of tags

    Returns
    -------
    Queryset of surface, distinct
    """
    from .models import Surface

    surface_ids = [s.id for s in surfaces]
    tag_ids = [tag.id for tag in tags]

    surfaces = Surface.objects.filter(id__in=surface_ids)
    surfaces |= Surface.objects.filter(tags__in=tag_ids)

    return surfaces.distinct().order_by('id')


def selection_to_instances(selection):
    """Returns a tuple with querysets of explicitly selected topographies, surfaces, and tags.

    View permission is not checked.

    :param selection: selection list as saved in session
    :return: tuple (topographies, surfaces, tags)

    The returned tuple has 3 elements:

     'topographies': all topographies explicitly found in the selection
     'surfaces': all surfaces explicitly found in the selection (not only because its topography was selected)
     'tags': all tags explicitly found in the selection (not only because all related items are selected)

    Also surfaces without topographies are returned in 'surfaces' if selected.
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
        elif type == 'tag':
            tag_ids.add(id)

    topographies = Topography.objects.filter(id__in=topography_ids)
    surfaces = Surface.objects.filter(id__in=surface_ids)
    tags = TagModel.objects.filter(id__in=tag_ids)

    return topographies, surfaces, tags


def selected_instances(request):
    """Return a tuple with topography, surface, and tag instances which are currently selected.

    View permission is checked for the user of the request.

    :request: HTTP request
    :return: tuple (topographies, surfaces, tags)

    The returned tuple has 3 elements, each a list:

     'topographies': all topographies in the selection (if 'surface' is given, filtered by this surface)
     'surfaces': all surfaces explicitly found in the selection (not only because its topography was selected)
     'tags': all tags explicitly found in selection (not because all tagged items are selected)

    Also surfaces without topographies are returned in 'surfaces' if selected.

    If only one topography is selected, it's surface is *not* returned in 'surfaces'.
    If a surface is explicitly selected, all of its topographies are contained in 'topographies'.
    """
    selection = selection_from_session(request.session)
    topographies, surfaces, tags = selection_to_instances(selection)

    # make sure that only topographies with read permission can be found here
    topographies = [t for t in topographies
                    if request.user.has_perm('view_surface', t.surface)]
    surfaces = [s for s in surfaces
                if request.user.has_perm('view_surface', s)]

    return topographies, surfaces, list(tags)


def instances_to_basket_items(topographies, surfaces, tags):
    """

    Parameters
    ----------
    topographies
    surfaces
    tags

    Returns
    -------
    List of items in the basket. Each is a dict with keys

     label, type, unselect_url, key

    Example with one selected surface:

     [ {'label': "Test Surface",
        'type': "surface",
        'unselect_url': ".../manager/surface/13/unselect",
        'key': "surface-13"}
     ]

    """
    basket_items = []
    for s in surfaces:
        unselect_url = reverse('manager:surface-unselect', kwargs=dict(pk=s.pk))
        basket_items.append(dict(label=str(s),
                                 type="surface",
                                 unselect_url=unselect_url,
                                 key=f"surface-{s.pk}"))
    for topo in topographies:
        unselect_url = reverse('manager:topography-unselect', kwargs=dict(pk=topo.pk))
        basket_items.append(dict(label=topo.name,
                                 type="topography",
                                 unselect_url=unselect_url,
                                 key=f"topography-{topo.pk}",
                                 surface_key=f"surface-{topo.surface.pk}"))
    for tag in tags:
        unselect_url = reverse('manager:tag-unselect', kwargs=dict(pk=tag.pk))
        basket_items.append(dict(label=tag.name,
                                 type="tag",
                                 unselect_url=unselect_url,
                                 key=f"tag-{tag.pk}"))

    return basket_items


def current_selection_as_basket_items(request):
    """Returns current selection as JSON suitable for the basket.

    Parameters
    ----------
    request

    Returns
    -------
    List of items in the basket. Each is a dict with keys

     label, type, unselect_url, key

    Example with one selected surface:

     [ {'label': "Test Surface",
        'type': "surface",
        'unselect_url': ".../manager/surface/13/unselect",
        'key': "surface-13"}
     ]

    """
    topographies, surfaces, tags = selected_instances(request)
    return instances_to_basket_items(topographies, surfaces, tags)


def subjects_to_json(subjects):
    """Return JSON code suitable for passing 'subjects_ids' in AJAX call.

    Parameters
    ----------
    subjects: sequence of Topography or Surface

    Returns
    -------
    As JSON: dict with

        key: content_type id as str (only strings can be keys in JSON hashes)
        values: array of integers with object ids for given content type (key)

    Each content type from the given subjects is represented as key.
    Each subject is represented by an id in the array of integers.
    """
    tmp = {}  # key: ContentType, value: list of subject ids
    for sub in subjects:
        ct = ContentType.objects.get_for_model(sub)  # uses cache internally
        if ct not in tmp:
            tmp[ct] = []
        tmp[ct].append(sub.id)

    result = {
        ct.id: sub_ids for ct, sub_ids in tmp.items()
    }
    return json.dumps(result)


def subjects_from_json(subjects_ids_json, function=None):
    """Return subject instances from ids given as json, optionally filtered.

    Parameters
    ----------
    subjects_ids_json: JSON encoded dict with

        key: content_type id as str (only strings can be keys in JSON hashes)
        values: array of integers with object ids for given content type (key)

        Each content type from the given subjects is represented as key.
        Each subject is represented by an id in the array of integers.

    function: AnalysisFunction instance or None
        If given an analysis function, the subjects returned will
        be filtered so only subjects are included which have
        an implementation for the given function.

    Returns
    -------
    sequence of subject instances (e.g. Topography or Surface)

    """
    subjects_ids = json.loads(subjects_ids_json)
    subjects = []
    for subject_type_id_str, subject_object_ids in subjects_ids.items():
        ct = ContentType.objects.get_for_id(int(subject_type_id_str))  # keys in JSON hashes are always string
        if function:
            if not function.is_implemented_for_type(ct):
                # skip these subjects
                continue
        for so_id in subject_object_ids:
            subjects.append(ct.get_object_for_this_type(id=so_id))
    return subjects


def selection_to_subjects_json(request):
    """Convert current selection into list of subjects as json.

    Parameters
    ----------
    request

    Returns
    -------
    (eff_topographies, eff_surfaces, subjects_ids_json)

    where:
        eff_topographies  - list of topographies which are effectively
                            included in the selection (selected explicitly
                            or implicitly by surfaces and tags)
        eff_surfaces      - list of surfaces which are effectively
                            included in the selection (by selecting surfaces+tags)
        subjects_ids_json - JSONfied dict with key: content type id, value: list of object ids
                            This dict encodes all subjects in the selection

    The eff_ results can be used for selection which tabs should be shown in the UI.
    This was the original purpose for returning them here.
    """
    topographies, surfaces, tags = selected_instances(request)
    effective_topographies = instances_to_topographies(topographies, surfaces, tags)
    effective_surfaces = instances_to_surfaces(surfaces, tags)

    # Do we have permission for all of these?
    user = request.user
    effective_topographies = [t for t in effective_topographies if user.has_perm('view_surface', t.surface)]
    effective_surfaces = [s for s in effective_surfaces if user.has_perm('view_surface', s)]

    # we collect effective topographies and surfaces because we have so far implementations
    # for analysis functions for topographies and surfaces
    subjects_ids_json = subjects_to_json(effective_topographies+effective_surfaces)

    return effective_topographies, effective_surfaces, subjects_ids_json


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
    """Returns an entry for bandwidths data.

    :param topo: topobank.manager.models.Topography instance
    :return: dict
    """

    err_message = None

    try:
        st_topo = topo.topography()  # st_: from SurfaceTopography
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
                'topography': topo,
                'link': link,
                'error_message': err_message
        }

    try:
        unit = st_topo.info['unit']
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

        lower_bound, upper_bound = st_topo.bandwidth()
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
            'topography': topo,
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
    'topo': topography instance
    'link': link to topography details
    'error_message': None or a string with an error message if calculation failed

    The list is sorted by the lower bound with smaller lower bound first.

    The idea is to be able to display error messages and the links
    also on javascript level which gets this data.
    """
    bandwidths_data = [ _bandwidths_data_entry(t) for t in topographies]

    #
    # Sort by lower bound, put lower bound=None first to show error messages first in plot
    #
    def weight(entry):
        lb = entry['lower_bound']
        return float('-inf') if lb is None else lb  # so errors appear first

    bandwidths_data.sort(key=lambda entry: weight(entry))

    return bandwidths_data


def get_search_term(request) -> str:
    """Extract a search term from given request.

    The search term is truncated at a maximum
    size of MAX_LEN_SEARCH_TERM.

    Parameters
    ----------
    request

    Returns
    -------
    String with search term, an empty string if no term was given.

    """
    search_term = request.GET.get('search', default='')
    search_term = search_term[:MAX_LEN_SEARCH_TERM]
    return search_term.strip()


def get_category(request) -> str:
    """Extract a surface category from given request.

    Parameters
    ----------
    request

    Returns
    -------
    String with requested category.

    Raises
    ------
    PermissionDenied() if an unknown category was given.
    """
    from .views import CATEGORY_FILTER_CHOICES
    category = request.GET.get('category', default='all')
    if category not in CATEGORY_FILTER_CHOICES.keys():
        raise PermissionDenied()
    return category


def get_sharing_status(request) -> str:
    """Extract a sharing status from given request.

     Parameters
     ----------
     request

     Returns
     -------
     String with requested sharing status.

     Raises
     ------
     PermissionDenied() if an unknown sharing status was given.
     """
    from .views import SHARING_STATUS_FILTER_CHOICES
    sharing_status = request.GET.get('sharing_status', default='all')
    if sharing_status not in SHARING_STATUS_FILTER_CHOICES.keys():
        raise PermissionDenied()
    return sharing_status


def get_tree_mode(request) -> str:
    """Extract tree_mode from given request.

     Parameters
     ----------
     request

     Returns
     -------
     String with requested tree mode.

     Raises
     ------
     PermissionDenied() if an unknown sharing status was given.
     """
    from .views import TREE_MODE_CHOICES
    tree_mode = request.GET.get('tree_mode', default='surface list')
    if tree_mode not in TREE_MODE_CHOICES:
        raise PermissionDenied()
    return tree_mode


def get_firefox_webdriver() -> WebDriver:

    binary = FirefoxBinary(str(settings.FIREFOX_BINARY_PATH))

    options = webdriver.firefox.options.Options()
    options.add_argument("--headless")

    return webdriver.Firefox(
        options=options,
        firefox_binary=binary,
        executable_path=str(settings.GECKODRIVER_PATH),
        service_log_path=devnull,
    )
