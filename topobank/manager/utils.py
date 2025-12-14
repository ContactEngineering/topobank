import base64
import functools
import json
import logging
import os
import tempfile
import traceback
from typing import Optional

import markdown2
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.files import File
from django.db import models
from rest_framework.reverse import reverse
from SurfaceTopography import open_topography
from SurfaceTopography.IO import ReaderBase
from SurfaceTopography.IO import readers as surface_topography_readers
from SurfaceTopography.IO.DZI import write_dzi

_log = logging.getLogger(__name__)


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


def mangle_content_type(obj, default_app_label="manager"):
    """Mangle content type into a string that can be used as a Javascript variable name"""
    if not isinstance(obj, ContentType):
        obj = ContentType.objects.get_for_model(obj)
    app_label, name = obj.natural_key()
    if app_label == default_app_label:
        return name
    else:
        return f"{app_label}_{name}"


def demangle_content_type(s, default_app_label="manager"):
    """Return content type given its mangled string representation"""
    s = s.split("_", maxsplit=1)
    if len(s) == 1:
        return ContentType.objects.get_by_natural_key(default_app_label, *s)
    else:
        return ContentType.objects.get_by_natural_key(*s)


def get_reader_infos():
    reader_infos = []
    for reader_class in surface_topography_readers:
        # noinspection PyBroadException
        try:
            # some reader classes have no description yet
            descr = reader_class.description()
        except Exception:
            descr = "*description not yet available*"

        descr = markdown2.markdown(descr, extras=["fenced-code-blocks"])

        reader_infos.append((reader_class.name(), reader_class.format(), descr))

    return reader_infos


def get_topography_reader(
    filefield: models.FileField, format: Optional[str] = None
) -> ReaderBase:
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
    if not hasattr(filefield, "mode"):
        # Workaround such that the SurfaceTopography module recognizes this as a binary
        # stream
        filefield.mode = "rb"
    if hasattr(filefield.file, "seek"):
        # make sure the file is rewound
        filefield.file.seek(0)
    reader = open_topography(filefield, format=format)
    return reader


def subjects_to_dict(subjects):
    """
    Returns a dictionary suitable for passing subjects (topography,
    surfaces or surface collections) in an AJAX call.

    Each content type from the given subjects is represented as key.
    Each subject is represented by an id in the array of integers.

    Parameters
    ----------
    subjects : list of Topography or Surface or Tag
        Subjects for serialization

    Returns
    -------
    A dictionary with
        key : str
            Mangled content type string
        values : list
            Integers with object ids for given content type (key)
    """
    tmp = {}  # key: ContentType, value: list of subject ids
    for sub in subjects:
        ct = ContentType.objects.get_for_model(sub)  # uses cache internally
        if ct not in tmp:
            tmp[ct] = []
        if ct.name == "tag":
            tmp[ct].append(sub.name)
        else:
            tmp[ct].append(sub.id)

    return {mangle_content_type(ct): sub_ids for ct, sub_ids in tmp.items()}


def subjects_from_dict(subjects_dict, user=None, function=None):
    """
    Return subject instances from ids given as a dictionary.

    Each content type from the given subjects is represented as key.
    Each subject is represented by an id in the array of integers.

    Parameters
    ----------
    subjects_dict : dict
        A dictionary with
            key : str
                Mangled content type string
            values : list
                Integers with object ids for given content type (key)
    user : topobank.users.models.User, optional
        User object. Function performs a permissions check if present.
        (Default: None)
    function : Workflow, optional
        If given an analysis function, the subjects returned will
        be filtered so only subjects are included which have
        an implementation for the given function. (Default: None)

    Returns
    -------
    List of subject instances (e.g. Topography or Surface)
    """

    # Build list with potential subjects
    subjects = []
    for subject_app_label_and_model, subject_ids in subjects_dict.items():
        ct = demangle_content_type(subject_app_label_and_model)
        if function:
            if not function.is_implemented_for_type(ct):
                # skip these subjects
                continue
        query = None
        for so_id in subject_ids:
            if ct.name == "tag":
                q = models.Q(name=so_id)
            else:
                q = models.Q(id=so_id)
            query = q if query is None else query | q
        if query is None:
            # skip these subjects
            continue
        subjects += [s for s in ct.get_all_objects_for_this_type().filter(query)]

    if subjects == []:
        # Skip permissions check
        return []

    # Check permissions is user is specified
    if user is not None:
        # Build list of related surfaces
        related_surfaces = [s.get_related_surfaces() for s in subjects]
        if related_surfaces == []:
            # Nothing to check
            return []
        unique_surfaces = set(
            [s for s in functools.reduce(lambda x, y: x + y, related_surfaces, [])]
        )
        if len(unique_surfaces) == 0:
            # Nothing to check (but should not really happen)
            return []
        permissions = [
            all([s.has_permission(user, "view") for s in r]) for r in related_surfaces
        ]

        # Filter only those subjects that have view permissions
        subjects = [s for s, p in zip(subjects, permissions) if p]

    return subjects


def dict_to_base64(d):
    """URL-safe base64 encoding of a dictionary."""
    return base64.urlsafe_b64encode(json.dumps(d).encode()).decode()


def dict_from_base64(s):
    """Return dictionary given a base64 encoded variant"""
    return json.loads(base64.urlsafe_b64decode(s.encode()).decode())


def subjects_to_base64(subjects):
    """
    Turns and encode URL into a list of subjects.

    Parameters
    ----------
    url : str
        Encoded subjects

    Returns
    -------
    List of subject instances (e.g. Topography or Surface)
    """
    return dict_to_base64(subjects_to_dict(subjects))


def subjects_from_base64(subjects, user=None, function=None):
    """
    Returns a string suitable for passing subjects (topography,
    surfaces or surface collections) in an URL.

    Parameters
    ----------
    subjects : list of Topography or Surface or Tag
        Subjects for serialization

    Returns
    -------
    Encoded dictionary object.
    """
    return subjects_from_dict(dict_from_base64(subjects), user=user, function=function)


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

    body = (
        "Hey there,\n\n"
        "I've problems with 'contact.engineering'.\n\nHere are some details:\n\n"
        f"Context: {info}\n"
        f"Error message: {err_msg}\n"
    )

    body += "Traceback:\n"

    body += "-" * 72 + "\n"
    body += f"\n{traceback}\n"
    body += "-" * 72 + "\n"
    body += "\n\nBest, <your name>"

    # change characters to we can use this in a link
    body = body.replace("\n", "%0D%0A")
    return body


def _bandwidths_data_entry(topo):
    """Returns an entry for bandwidths data.

    :param topo: topobank.manager.models.Topography instance
    :return: dict
    """

    lower_bound = topo.bandwidth_lower
    upper_bound = topo.bandwidth_upper

    err_message = None
    if lower_bound is None or upper_bound is None:
        err_message = f"Bandwidth for measurement '{topo.name}' is not yet available."
        link = mailto_link_for_reporting_an_error(
            f"Failure determining bandwidth (id: {topo.id})",
            "Bandwidth data calculation",
            err_message,
            traceback.format_exc(),
        )
    else:
        link = reverse("manager:topography-api-detail", kwargs=dict(pk=topo.pk))

    short_reliability_cutoff = topo.short_reliability_cutoff

    return {
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
        "topography": topo,
        "link": link,
        "error_message": err_message,
        "short_reliability_cutoff": short_reliability_cutoff,
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
    'short_reliability_cutoff': limit of the unreliable bandwidth (or None if all data is reliable) in meters

    The list is sorted by the lower bound with smaller lower bound first.

    The idea is to be able to display error messages and the links
    also on javascript level which gets this data.
    """
    bandwidths_data = [_bandwidths_data_entry(t) for t in topographies]

    #
    # Sort by lower bound, put lower bound=None first to show error messages first in plot
    #
    def weight(entry):
        lb = entry["lower_bound"]
        return float("-inf") if lb is None else lb  # so errors appear first

    bandwidths_data.sort(key=lambda entry: weight(entry))

    return bandwidths_data


def render_deepzoom(
    data,
    folder,
    physical_sizes=None,
    unit=None,
    quality=95,
    colorbar_title=None,
    cmap=None,
    storage_prefix="",
    generate_netcdf=True,
):
    """
    Make JPG Deep Zoom Image (DZI) files given data on a two-dimensional grid.

    The DZI format specifies multiple files:
        1. A JSON file containing structural information on the file
        2. A set of image files at different zoom levels

    Optionally also generates NetCDF tiles for the interactive Three.js viewer.

    Parameters
    ----------
    data : :obj:SurfaceTopography.Topogaphy or :obj:numpy.ndarray
        Data container holding the 2D data set.
    folder : topobank.files.models.Folder
        Folder containing the Deep Zoom Image files.
    physical_sizes : tuple of float, optional
        Physical sizes of the two-dimensional map, if not specified by `data`.
        (Default: None)
    unit : str, optional
        Length unit of the physical sizes, if not specified by `data`.
        (Default: None)
    quality : int, optional
        Quality of JPG, passed to Pillow's `save` function.
    colorbar_title : str, optional
        Title of colorbar; this information is dumped into the metadata json
        and a proprietary extension to the official DZI format.
        (Default: None)
    cmap : str, optional
        Name of colormap; this information is dumped into the metadata json
        and a proprietary extension to the official DZI format.
        (Default: None)
    storage_prefix : str, optional
        Prefix to attach in front of the DZI filenames. (Default: '')
    generate_netcdf : bool, optional
        If True, also generate NetCDF tiles alongside JPG tiles for the
        interactive Three.js viewer. (Default: True)
    """
    with tempfile.TemporaryDirectory() as tmpdirname:
        try:
            # This is a Topography
            filenames = data.to_dzi(
                "dzi",
                root_directory=tmpdirname,
                meta_format="json",
                quality=quality,
                cmap=cmap,
            )
        except AttributeError:
            # This is likely just a numpy array
            if physical_sizes is None or unit is None:
                raise ValueError(
                    "You need to provide `physical_sizes` and `unit` when visualizing "
                    "numpy arrays."
                )
            filenames = write_dzi(
                data,
                "dzi",
                physical_sizes,
                unit,
                root_directory=tmpdirname,
                meta_format="json",
                quality=quality,
                colorbar_title=colorbar_title,
                cmap=cmap,
            )
        for filename in filenames:
            # Strip tmp directory
            storage_filename = os.path.join(
                storage_prefix, filename[len(tmpdirname) + 1 :]
            )
            # Upload to S3
            folder.save_file(storage_filename, "der", File(open(filename, mode="rb")))

        # Generate NetCDF tiles for interactive viewer
        if generate_netcdf:
            try:
                # This is a Topography
                nc_filenames = data.to_dzi(
                    "dzi-nc",
                    root_directory=tmpdirname,
                    meta_format="json",
                    format="nc",
                )
            except AttributeError:
                # This is likely just a numpy array
                if physical_sizes is not None and unit is not None:
                    nc_filenames = write_dzi(
                        data,
                        "dzi-nc",
                        physical_sizes,
                        unit,
                        root_directory=tmpdirname,
                        meta_format="json",
                        format="nc",
                    )
                else:
                    nc_filenames = []
            for filename in nc_filenames:
                # Strip tmp directory
                storage_filename = os.path.join(
                    storage_prefix, filename[len(tmpdirname) + 1 :]
                )
                # Upload to S3
                folder.save_file(
                    storage_filename, "der", File(open(filename, mode="rb"))
                )
