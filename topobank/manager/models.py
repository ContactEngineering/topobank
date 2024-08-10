"""
Basic models for the web app for handling topography data.
"""

import io
import logging
import os.path
import sys
import tempfile
from collections import defaultdict
from typing import Union

import dateutil.parser
import django.dispatch
import matplotlib.pyplot
import numpy as np
import PIL
import pint
import tagulous.models as tm
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.validators import MinValueValidator
from django.db import models
from rest_framework.reverse import reverse
from guardian.models import GroupObjectPermissionBase, UserObjectPermissionBase
from guardian.shortcuts import (
    assign_perm,
    get_perms,
    get_users_with_perms,
    remove_perm,
    get_objects_for_user,
)
from notifications.signals import notify
from SurfaceTopography.Container.SurfaceContainer import SurfaceContainer
from SurfaceTopography.Exceptions import UndefinedDataError
from SurfaceTopography.Support.UnitConversion import get_unit_conversion_factor

from ..taskapp.models import TaskStateModel
from ..taskapp.utils import run_task
from ..users.models import User
from .utils import (
    api_to_guardian,
    dzi_exists,
    generate_upload_path,
    get_topography_reader,
    guardian_to_api,
    make_dzi,
    recursive_delete
)

_log = logging.getLogger(__name__)
_ureg = pint.UnitRegistry()

post_renew_cache = django.dispatch.Signal()

MAX_LENGTH_DATAFILE_FORMAT = (
    15  # some more characters than currently needed, we may have sub formats in future
)
MAX_NUM_POINTS_FOR_SYMBOLS_IN_LINE_SCAN_PLOT = 100
SQUEEZED_DATAFILE_FORMAT = "nc"

# Detect whether we are running within a Celery worker. This solution was suggested here:
# https://stackoverflow.com/questions/39003282/how-can-i-detect-whether-im-running-in-a-celery-worker
_IN_CELERY_WORKER_PROCESS = (
    sys.argv and sys.argv[0].endswith("celery") and "worker" in sys.argv
)


# Deprecated, but needed for migrations
def user_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/user_<id>/<filename>
    return "topographies/user_{0}/{1}".format(instance.surface.creator.id, filename)


def _get_unit(channel):
    if isinstance(channel.unit, tuple):
        lateral_unit, data_unit = channel.unit
        return data_unit
    return channel.unit


class ThumbnailGenerationException(Exception):
    """Failure while generating thumbnails for a topography."""

    def __init__(self, topo, message):
        self._topo = topo
        self._message = message

    def __str__(self):
        return self._message


class DZIGenerationException(ThumbnailGenerationException):
    """Failure while generating DZI files for a topography."""

    pass


class SubjectMixin:
    """Extra methods common to all instances which can be subject to an analysis."""

    # This is needed for objects to be able to serve as subjects
    #     for analysis, because some template code uses this.
    # Probably this could be made faster by caching the result.
    # Not sure whether this should be done at compile time.
    @classmethod
    def get_content_type(cls):
        """Returns ContentType for own class."""
        return ContentType.objects.get_for_model(cls)

    @classmethod
    def get_subject_type(cls):
        """Returns a human readable name for this subject type."""
        return cls._meta.model_name

    def is_shared(self, with_user, allow_change=False):
        """Returns True, if this subject is shared with a given user.

        Always returns True if user is the creator of the related surface.

        :param with_user: User to test
        :param allow_change: If True, only return True if surface can be changed by given user
        :return: True or False
        """
        raise NotImplementedError()

    def get_related_surfaces(self):
        """Returns a list of related surfaces. This can be either the parent
        surface (for a topography), the child surfaces (for a tag), or the
        surface itself (for a surface).

        Returns
        -------
        surfaces : list of Surface
            The surfaces that are related to this object.
        """
        raise NotImplementedError()

    def get_users_with_perms(self):
        """Return users with any permission on this subject.

        Returns
        -------
        users : Queryset of users
            All users that have some form of permission (view, full, etc.) on
            this subject.
        """
        return User.objects.intersection(
            *tuple(get_users_with_perms(s) for s in self.get_related_surfaces())
        )


class Tag(tm.TagTreeModel, SubjectMixin):
    """This is the common tag model for surfaces and topographies."""

    class TagMeta:
        force_lowercase = True
        # not needed yet
        # autocomplete_view = 'manager:autocomplete-tags'

    _user = None

    def authenticate_user(self, user):
        self._user = user

    def is_shared(self, with_user, allow_change=False):
        return True  # Tags are generally shared, but the surfaces may not

    def get_related_surfaces(self):
        """Return all surfaces with exactly this tag"""
        if self._user is None:
            raise PermissionError(
                "Cannot return surfaces belonging to a tag because "
                "no user was specified. Use `authenticate_user` "
                "to restrict user permissions."
            )
        return Surface.objects.for_user(self._user).filter(tags=self.id)

    def get_descendant_surfaces(self):
        """Return all surfaces with exactly this tag or a descendant tag"""
        if self._user is None:
            raise PermissionError(
                "Cannot return surfaces belonging to a tag because "
                "no user was specified. Use `authenticate_user` "
                "to restrict user permissions."
            )
        return Surface.objects.for_user(self._user).filter(tags__path__startswith=self.path)

    def get_properties(self, kind=None):
        """
        Collects unique properties for a given tag based on the kind of property.

        Parameters
        ----------
        self : Tag
            The tag to collect unique properties for.
        kind : str, optional
            The kind of property to collect. Can be 'categorical', 'numerical', or None.
            If None, collects all properties. Default is None.

        Raises
        ------
        ValueError
            If the kind is not None, 'categorical', or 'numerical'.

        Returns
        -------
        property_values : dict
            Keys are property names and values are lists of property values for
            each surface related to the tag.
        property_infos : dict
            Keys are property names and values are either a list of categories for
            categorical properties or a dictionary with min and max values for
            numerical properties.
        """
        if kind not in [None, "categorical", "numerical"]:
            raise ValueError(f"Invalid value for kind: {kind}")

        nb_surfaces = len(self.get_related_surfaces())

        # Initialize a dictionary to collect all properties. The default value for
        # each property is a list of np.nan of length equal to the number of
        # surfaces.
        property_values = defaultdict(lambda: [np.nan] * nb_surfaces)
        categorical_properties = set()

        # Iterate over all surfaces related to the tag
        for i, surface in enumerate(self.get_related_surfaces()):
            # For each surface, iterate over all its properties
            for p in Property.objects.filter(surface=surface):
                # If the property is categorical, add its name to the set of
                # categorical properties and set its value for the current surface
                if p.is_categorical:
                    categorical_properties.add(str(p.name))
                    if kind is None or kind == "categorical":
                        property_values[str(p.name)][i] = p.value
                # If the property is not categorical, set its value for the
                # current surface (np.nan if the value is None)
                elif kind is None or kind == "numerical":
                    property_values[str(p.name)][i] = (
                        np.nan if p.value is None else p.value
                    )

        # Initialize a dictionary to store additional information about each property
        property_infos = {}

        # For each property, if it's categorical, store its categories (excluding
        # np.nan). If it's numerical, store its min and max values.
        for key, values in property_values.items():
            if key in categorical_properties:
                property_infos[key] = {"categories": list(set(values) - set([np.nan]))}
            else:
                property_infos[key] = {
                    "min_value": np.nanmin(values),
                    "max_value": np.nanmax(values),
                }

        return property_values, property_infos


class TopobankLazySurfaceContainer(SurfaceContainer):
    """Wraps a `Surface` with lazy loading of topography data"""

    def __init__(self, surface):
        self._surface = surface
        self._topographies = self._surface.topography_set.all()

    def __len__(self):
        return len(self._topographies)

    def __getitem__(self, item):
        return self._topographies[item].read()


class SurfaceManager(models.Manager):
    def for_user(self, user: User, perms: list[str] = ["view_surface"]):
        """Return a queryset of all surfaces, the user has *all* given permissions.

        :param user: user for which we want to know the surfaces
        :param perms: list of permission codenames, default is ['view_surface']
        :return: queryset of surfaces
        """
        return get_objects_for_user(
            user, perms, klass=Surface, accept_global_perms=False
        )


class Surface(models.Model, SubjectMixin):
    """
    A physical surface of a specimen.

    There can be many topographies (measurements) for one surface.
    """

    CATEGORY_CHOICES = [
        ("exp", "Experimental data"),
        ("sim", "Simulated data"),
        ("dum", "Dummy data"),
    ]

    LICENSE_CHOICES = [
        (k, settings.CC_LICENSE_INFOS[k]["option_name"])
        for k in ["cc0-1.0", "ccby-4.0", "ccbysa-4.0"]
    ]

    objects = SurfaceManager()

    name = models.CharField(max_length=80, blank=True)
    creator = models.ForeignKey(User, on_delete=models.CASCADE)
    description = models.TextField(blank=True)
    category = models.CharField(
        max_length=3, choices=CATEGORY_CHOICES, null=True, blank=False
    )
    tags = tm.TagField(to=Tag)
    creation_datetime = models.DateTimeField(auto_now_add=True, null=True)
    modification_datetime = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        ordering = ["name"]
        permissions = (
            ("share_surface", "Can share surface"),
            ("publish_surface", "Can publish surface"),
        )

    def __str__(self):
        s = self.name
        if self.is_published:
            s += f" (version {self.publication.version})"
        return s

    @property
    def label(self):
        return str(self)

    @property
    def attachments(self):
        if not hasattr(self, "fileparent"):
            return []
        return self.fileparent.get_valid_files()

    def get_related_surfaces(self):
        return [self]

    def get_absolute_url(self, request=None):
        """URL of API endpoint for this surface"""
        return reverse(
            "manager:surface-api-detail", kwargs=dict(pk=self.pk), request=request
        )

    def num_topographies(self):
        return self.topography_set.count()

    def save(self, *args, **kwargs):
        created = self.pk is None
        super().save(*args, **kwargs)
        if created:
            self.grant_permissions_to_creator()

    def grant_permissions_to_creator(self):
        """Grant all permissions for this surface to its creator."""
        for perm in [
            "view_surface",
            "change_surface",
            "delete_surface",
            "share_surface",
            "publish_surface",
        ]:
            assign_perm(perm, self.creator, self)

    def to_dict(self):
        """Create dictionary for export of metadata to json or yaml.

        Does not include topographies. They can be added like this:

         surface_dict = surface.to_dict()
         surface_dict['topographies'] = [t.to_dict() for t in surface.topography_set.order_by('name')]

        The publication URL will be based on the official contact.engineering URL.

        Returns:
            dict
        """
        creator = {"name": self.creator.name}
        if self.creator.orcid_id is not None:
            creator["orcid"] = self.creator.orcid_id
        d = {
            "name": self.name,
            "category": self.category,
            "creator": creator,
            "description": self.description,
            "tags": [t.name for t in self.tags.order_by("name")],
            "is_published": self.is_published,
        }
        if self.is_published:
            d["publication"] = {
                "url": self.publication.get_full_url(),
                "license": self.publication.get_license_display(),
                "authors": self.publication.get_authors_string(),
                "version": self.publication.version,
                "date": str(self.publication.datetime.date()),
                "doi_url": self.publication.doi_url or "",
                "doi_state": self.publication.doi_state or "",
            }
        if self.properties.count() > 0:
            d["properties"] = [p.to_dict() for p in self.properties.all()]
        return d

    def get_permissions(self, with_user):
        """
        Return current access permissions.


        Parameters
        ----------
        with_user : User object
            User to share the surface with.

        Returns
        -------
        permissions : str
            Permissions string
                'no-access': No access to the dataset
                'view': Basic view access, corresponding to 'view_surface'
                'edit': Edit access, corresponding to 'view_surface' and
                    'change_surface'
                'full': Full access (essentially transfer), corresponding to
                    'view_surface', 'change_surface', 'delete_surface',
                    'share_surface' and 'publish_surface':
        """
        return guardian_to_api(get_perms(with_user, self))

    def is_shared(self, with_user):
        """
        Returns True if this surface is shared with a given user.

        Always returns True if the user is the creator of the surface.

        Parameters
        ----------
        with_user : User
            The user to check for sharing status.

        Returns
        -------
        bool
            True if the surface is shared with the given user, False otherwise.
        """
        return self.get_permissions(with_user) != "no-access"

    def set_permissions(self, with_user, permissions):
        """
        Set permissions for access to this surface for a given user.
        This is equivalent to sharing the dataset.

        Parameters
        ----------
        with_user : User object
            User to share the surface with.
        permissions : str
            Permissions string
                'no-access': No access to the dataset
                'view': Basic view access, corresponding to 'view_surface'
                'edit': Edit access, corresponding to 'view_surface' and
                    'change_surface'
                'full': Full access (essentially transfer), corresponding to
                    'view_surface', 'change_surface', 'delete_surface',
                    'share_surface' and 'publish_surface'
        """
        if self.is_published:
            raise PermissionError(
                "Permissions of a published digital surface twin cannot be changed."
            )

        all_perms = set(api_to_guardian("full"))
        user_perms = set(api_to_guardian(permissions))

        # Revoke all permissions not in the set
        for perm in all_perms - user_perms:
            remove_perm(perm, with_user, self)

        # Assign all permissions
        for perm in user_perms:
            assign_perm(perm, with_user, self)

    def share(self, with_user):
        """Set permissions for read-only access to this surface for a given
        user. This is equivalent to sharing the dataset.

        Parameters
        ----------
        with_user : User object
            User to share the surface with.
        """
        self.set_permissions(with_user, "view")

    def unshare(self, with_user):
        """Revoke access to this surface for a given user.
        This is equivalent to unsharing the dataset.

        Parameters
        ----------
        with_user : User object
            User to share the surface with.
        """
        self.set_permissions(with_user, "no-access")

    def deepcopy(self):
        """Creates a copy of this surface with all topographies and meta data.

        The database entries for this surface and all related
        topographies are copied, therefore all meta data.
        All files will be copied.

        References to instruments will not be copied.

        The automated analyses will be triggered for this new surface.

        Returns
        -------
        The copy of the surface.

        """
        # Copy of the surface entry
        # (see https://docs.djangoproject.com/en/2.2/topics/db/queries/#copying-model-instances)

        surface = Surface.objects.get(pk=self.pk)
        surface.pk = None
        surface.task_id = None  # We need to indicate that no tasks have run
        surface.tags = self.tags.get_tag_list()
        surface.save()

        for topography in self.topography_set.all():
            topography.deepcopy(surface)
            # we pass the surface here because there is a constraint that (surface_id + topography name)
            # must be unique, i.e. a surface should never have two topographies of the same name,
            # so we can't set the new surface as the second step

        _log.info("Created deepcopy of surface %s -> surface %s", self.pk, surface.pk)
        return surface

    @property
    def is_published(self):
        """Returns True, if a publication for this surface exists."""
        return hasattr(
            self, "publication"
        )  # checks whether the related object surface.publication exists

    def lazy_read(self):
        """
        Returns a `SurfaceTopography.Container.SurfaceContainer`
        representation of this dataset. Reading of actual data is deferred
        to the point where it is actually needed.
        """
        return TopobankLazySurfaceContainer(self)


class Property(models.Model):
    class Meta:
        unique_together = (("surface", "name"),)
        verbose_name_plural = "properties"

    name = models.TextField(default="prop")
    value_categorical = models.CharField(blank=True, null=True)
    value_numerical = models.FloatField(blank=True, null=True)
    unit = models.TextField(null=True, blank=True)
    surface = models.ForeignKey(
        Surface, on_delete=models.CASCADE, related_name="properties"
    )

    @property
    def value(self):
        if self.value_numerical is None:
            return str(self.value_categorical)
        return float(self.value_numerical)

    @value.setter
    def value(self, value):
        """
        Set the value of the property.

        Parameters:
        - value (int, float, str): The value to be assigned. Should be of type int, float, or str.

        Raises:
        - TypeError: If the provided value is not of type int, float, or str.

        Notes:
        - If the value is of type str, it will be assigned to the 'value_categorical' attribute.
        - If the value is of type int or float, it will be assigned to the 'value_numerical' attribute.
        """
        if isinstance(value, str):
            self.value_categorical = value
            self.value_numerical = None
        elif isinstance(value, float) or isinstance(value, int):
            self.value_numerical = value
            self.value_categorical = None
        else:
            raise TypeError(
                f"The value must be of type int, float or str, got {type(value)}"
            )

    def validate(self):
        """
        Checks the invariants of this Model.
        If any invariant is broken, a ValidationError is raised

        Invariants:
        - 1. `value_categorical` or `value_numerical` are `None`
        - 2. `value_categorical` or `value_numerical` are not `None`
        This results in a 'XOR' logic and exaclty one of the value fields has to hold a value
        - 3. if `value_categorical` is not `None`, unit is `None`

        This enforces the definition of a categorical values -> no units.

        IMPORTANT!
        The opposite is not the case!
        If a unit is `None` this could also mean that its a numerical value, with no dimension
        """

        # Invariant 1
        if not (self.value_categorical is None or self.value_numerical is None):
            raise ValidationError(
                "Either 'value_categorical' or 'value_numerical' must be None."
            )
        # Invariant 2
        if not (self.value_categorical is not None or self.value_numerical is not None):
            raise ValidationError(
                "Either 'value_categorical' or 'value_numerical' must be not None."
            )
        # Invariant 3
        if self.value_categorical is not None and self.unit is not None:
            raise ValidationError(
                "If the Property is categorical, the unit must be 'None'"
            )
        # Check unit
        if self.unit is not None:
            try:
                _ureg.check(str(self.unit))
            except pint.errors.UndefinedUnitError:
                raise ValidationError(f"Unit '{self.unit}' is not a physical unit")

    def save(self, *args, **kwargs):
        self.validate()
        super().save(*args, **kwargs)

    @property
    def is_numerical(self):
        return self.value_numerical is not None

    @property
    def is_categorical(self):
        return not self.is_numerical

    def __str__(self):
        if self.is_numerical:
            return f"{self.name}: {self.value} {self.unit}"
        else:
            return f"{self.name}: {self.value}"

    def to_dict(self):
        d = {"name": str(self.name), "value": self.value}
        if self.unit is not None:
            d["unit"] = str(self.unit)
        return d


class SurfaceUserObjectPermission(UserObjectPermissionBase):
    content_object = models.ForeignKey(Surface, on_delete=models.CASCADE)


class SurfaceGroupObjectPermission(GroupObjectPermissionBase):
    content_object = models.ForeignKey(Surface, on_delete=models.CASCADE)


def topography_datafile_path(instance, filename):
    return f"{instance.storage_prefix}/raw/{filename}"


def topography_squeezed_datafile_path(instance, filename):
    return f"{instance.storage_prefix}/nc/{filename}"


def topography_thumbnail_path(instance, filename):
    return f"{instance.storage_prefix}/thumbnail/{filename}"


class Topography(TaskStateModel, SubjectMixin):
    """
    A single topography measurement of a surface of a specimen.
    """

    # TODO After upgrade to Django 2.2, use constraints: https://docs.djangoproject.com/en/2.2/ref/models/constraints/
    class Meta:
        ordering = ["measurement_date", "pk"]
        unique_together = (("surface", "name"),)
        verbose_name_plural = "topographies"

    celery_queue = settings.TOPOBANK_MANAGER_QUEUE

    LENGTH_UNIT_CHOICES = [
        ("km", "kilometers"),
        ("m", "meters"),
        ("mm", "millimeters"),
        ("µm", "micrometers"),
        ("nm", "nanometers"),
        ("Å", "angstrom"),
        ("pm", "picometers"),  # This is the default unit for VK files so we need it
    ]

    HAS_UNDEFINED_DATA_DESCRIPTION = {
        None: "contact.engineering could not (yet) determine if this topography has undefined data points.",
        True: "The dataset has undefined/missing data points.",
        False: "No undefined/missing data found.",
    }

    FILL_UNDEFINED_DATA_MODE_NOFILLING = "do-not-fill"
    FILL_UNDEFINED_DATA_MODE_HARMONIC = "harmonic"

    FILL_UNDEFINED_DATA_MODE_CHOICES = [
        (FILL_UNDEFINED_DATA_MODE_NOFILLING, "Do not fill undefined data points"),
        (
            FILL_UNDEFINED_DATA_MODE_HARMONIC,
            "Interpolate undefined data points with harmonic functions",
        ),
    ]

    DETREND_MODE_CHOICES = [
        ("center", "No detrending, but subtract mean height"),
        ("height", "Remove tilt"),
        ("curvature", "Remove curvature and tilt"),
    ]

    INSTRUMENT_TYPE_UNDEFINED = "undefined"
    INSTRUMENT_TYPE_MICROSCOPE_BASED = "microscope-based"
    INSTRUMENT_TYPE_CONTACT_BASED = "contact-based"

    INSTRUMENT_TYPE_CHOICES = [
        (
            INSTRUMENT_TYPE_UNDEFINED,
            "Instrument of unknown type - all data considered as reliable",
        ),
        (
            INSTRUMENT_TYPE_MICROSCOPE_BASED,
            "Microscope-based instrument with known resolution",
        ),
        (
            INSTRUMENT_TYPE_CONTACT_BASED,
            "Contact-based instrument with known tip radius",
        ),
    ]

    verbose_name = "measurement"
    verbose_name_plural = "measurements"

    #
    # Descriptive fields
    #
    surface = models.ForeignKey("Surface", on_delete=models.CASCADE)
    name = models.TextField(
        blank=True
    )  # This must be identical to the file name on upload
    creator = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    measurement_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)
    tags = tm.TagField(to=Tag)
    creation_datetime = models.DateTimeField(auto_now_add=True, null=True)
    modification_datetime = models.DateTimeField(auto_now=True, null=True)

    #
    # Fields related to raw data
    #
    datafile = models.FileField(
        max_length=250, upload_to=topography_datafile_path, blank=True
    )  # currently upload_to not used in forms
    datafile_format = models.CharField(
        max_length=MAX_LENGTH_DATAFILE_FORMAT, null=True, default=None, blank=True
    )
    channel_names = models.JSONField(default=list)
    data_source = models.IntegerField(null=True)  # Channel index
    # Django documentation discourages the use of null=True on a CharField. I'll use it here
    # nevertheless, because I need this values as argument to a function where None has
    # a special meaning (autodetection of format). If I would use an empty string
    # as proposed in the docs, I would have to implement extra logic everywhere the field
    # 'datafile_format' is used.

    # All data is also stored in a 'squeezed' format for faster loading and processing
    # This is probably netCDF3. Scales and detrend has already been applied here.
    squeezed_datafile = models.FileField(
        max_length=260, upload_to=topography_squeezed_datafile_path, null=True
    )

    #
    # Fields with physical meta data
    #
    size_editable = models.BooleanField(default=False, editable=False)
    size_x = models.FloatField(null=True, validators=[MinValueValidator(0.0)])
    size_y = models.FloatField(
        null=True, validators=[MinValueValidator(0.0)]
    )  # null for line scans

    unit_editable = models.BooleanField(default=False, editable=False)
    unit = models.TextField(choices=LENGTH_UNIT_CHOICES, null=True)

    height_scale_editable = models.BooleanField(default=False, editable=False)
    height_scale = models.FloatField(default=1)

    has_undefined_data = models.BooleanField(
        null=True, default=None
    )  # default is undefined
    fill_undefined_data_mode = models.TextField(
        choices=FILL_UNDEFINED_DATA_MODE_CHOICES,
        default=FILL_UNDEFINED_DATA_MODE_NOFILLING,
    )

    detrend_mode = models.TextField(choices=DETREND_MODE_CHOICES, default="center")

    resolution_x = models.IntegerField(
        null=True, editable=False, validators=[MinValueValidator(0)]
    )  # null for line scans
    resolution_y = models.IntegerField(
        null=True, editable=False, validators=[MinValueValidator(0)]
    )  # null for line scans

    bandwidth_lower = models.FloatField(
        null=True, default=None, editable=False
    )  # in meters
    bandwidth_upper = models.FloatField(
        null=True, default=None, editable=False
    )  # in meters
    short_reliability_cutoff = models.FloatField(
        null=True, default=None, editable=False
    )

    is_periodic_editable = models.BooleanField(default=True, editable=False)
    is_periodic = models.BooleanField(default=False)

    #
    # Fields about instrument and its parameters
    #
    instrument_name = models.CharField(max_length=200, blank=True)
    instrument_type = models.TextField(
        choices=INSTRUMENT_TYPE_CHOICES, default=INSTRUMENT_TYPE_UNDEFINED
    )
    instrument_parameters = models.JSONField(default=dict)

    #
    # Other fields
    #
    thumbnail = models.ImageField(null=True, upload_to=topography_thumbnail_path)

    #
    # _refresh_dependent_data indicates whether caches (thumbnail, DZI) and analyses need to be refreshed after a call
    # to save()
    #
    _refresh_dependent_data = False

    # Changes in these fields trigger a refresh of the topography cache and of all analyses
    _significant_fields = {
        "size_x",
        "size_y",
        "unit",
        "is_periodic",
        "height_scale",
        "fill_undefined_data_mode",
        "detrend_mode",
        "data_source",
        "instrument_type",
    }  # + 'instrument_parameters'

    #
    # Methods
    #
    def save(self, *args, **kwargs):
        if self.creator is None:
            self.creator = self.surface.creator

        # Reset to no refresh
        self._refresh_dependent_data = False

        # Strategies to detect changes in significant fields:
        # https://stackoverflow.com/questions/1355150/when-saving-how-can-you-check-if-a-field-has-changed
        try:
            # Do not check for None in self.id as this breaks should we switch to UUIDs
            old_obj = Topography.objects.get(pk=self.pk)
        except self.DoesNotExist:
            pass  # Do nothing, we have just created a new topography
        else:
            # Check which fields actually changed
            changed_fields = [
                getattr(self, name) != getattr(old_obj, name)
                for name in self._significant_fields
            ]

            changed_fields = [
                name
                for name, changed in zip(self._significant_fields, changed_fields)
                if changed
            ]

            # `instrument_parameters` is special as it can contain non-significant entries
            if self._clean_instrument_parameters(
                self.instrument_parameters
            ) != self._clean_instrument_parameters(old_obj.instrument_parameters):
                changed_fields += ["instrument_parameters"]

            # We need to refresh if any of the significant fields changed during this save
            self._refresh_dependent_data = any(changed_fields)

            if self._refresh_dependent_data:
                _log.debug(
                    f"The following significant fields of topography {self.id} changed: "
                )
                for name in changed_fields:
                    _log.debug(
                        f"{name}: was '{getattr(old_obj, name)}', is now '{getattr(self, name)}'"
                    )

        # Save to data base
        _log.debug("Saving model...")
        if self.id is None and (
            self.datafile is not None
            or self.squeezed_datafile is not None
            or self.thumbnail is not None
        ):
            # We don't have an `id` but are trying to save a model with a data file; this does not work because the
            # `storage_prefix`  contains the `id`. (The `id` only becomes available once the model instance has
            # been saved.) Note that this situation is only relevant for tests.
            datafile = self.datafile
            squeezed_datafile = self.squeezed_datafile
            thumbnail = self.thumbnail
            # Since we do not have an id yet, we cannot store the file since we don't know where to put it
            self.datafile = None
            self.squeezed_datafile = None
            self.thumbnail = None
            # Save to get an id
            super().save(*args, **kwargs)
            # Now we have an id, so we can now save the files
            self.datafile = datafile
            self.squeezed_datafile = squeezed_datafile
            self.thumbnail = thumbnail
            kwargs.update(
                dict(
                    update_fields=["datafile", "squeezed_datafile", "thumbnail"],
                    force_insert=False,
                    force_update=True,
                )
            )  # The next save must be an update

        # Check if we need to run the update task
        if self._refresh_dependent_data:
            run_task(self)

        # Save after run task, because run task may update the task state
        super().save(*args, **kwargs)

        # Reset to no refresh
        self._refresh_dependent_data = False

    def delete(self, *args, **kwargs):
        self._remove_files()
        super().delete(*args, **kwargs)

    def _remove_files(self):
        """Remove files associated with a topography instance before removal of the topography."""

        # ideally, we would reuse datafiles if possible, e.g. for
        # the example topographies. Currently I'm not sure how
        # to do it, because the file storage API always ensures to
        # have unique filenames for every new stored file.

        def delete_datafile(datafile_attr_name):
            """Delete datafile attached to the given attribute name."""
            try:
                datafile = getattr(self, datafile_attr_name)
                _log.info(f"Deleting {datafile.name}...")
                datafile.delete()
            except Exception as exc:
                _log.warning(
                    f"Topography id {self.id}, attribute '{datafile_attr_name}': Cannot delete data file "
                    f"{self.name}', reason: {str(exc)}"
                )

        datafile_path = self.datafile.name
        squeezed_datafile_path = self.squeezed_datafile.name
        thumbnail_path = self.thumbnail.name

        delete_datafile("datafile")
        if self.has_squeezed_datafile:
            delete_datafile("squeezed_datafile")
        if self.has_thumbnail:
            delete_datafile("thumbnail")

        # Delete everything else after idiot check: Make sure files are actually stored under the storage prefix.
        # Otherwise we abort deletion.
        if datafile_path is not None and not datafile_path.startswith(
            self.storage_prefix
        ):
            _log.warning(
                f"Datafile is stored at location {datafile_path}, but storage prefix is "
                f"{self.storage_prefix}. I will not attempt to delete everything at this prefix."
            )
            return
        if (
            squeezed_datafile_path is not None
            and not squeezed_datafile_path.startswith(self.storage_prefix)
        ):
            _log.warning(
                f"Squeezed datafile is stored at location {squeezed_datafile_path}, but storage prefix is "
                f"{self.storage_prefix}. I will not attempt to delete everything at this prefix."
            )
            return
        if thumbnail_path is not None and not thumbnail_path.startswith(
            self.storage_prefix
        ):
            _log.warning(
                f"Thumbnail is stored at location {thumbnail_path}, but storage prefix is "
                f"{self.storage_prefix}. I will not attempt to delete everything at this prefix."
            )
            return
        recursive_delete(self.storage_prefix)

    def __str__(self):
        return "Topography '{0}' from {1}".format(self.name, self.measurement_date)

    @property
    def attachments(self):
        if not hasattr(self, "fileparent"):
            return []
        return self.fileparent.get_valid_files()

    @property
    def label(self):
        """Return a string which can be used in the UI."""
        return self.name

    @property
    def has_squeezed_datafile(self):
        """If True, a squeezed data file can be retrieved via self.squeezed_datafile"""
        return bool(self.squeezed_datafile)

    @property
    def has_thumbnail(self):
        """If True, a thumbnail can be retrieved via self.thumbnail"""
        if not bool(self.thumbnail):
            # thumbnail is not set
            return False
        # check whether it is a valid file
        from PIL import Image

        try:
            image = Image.open(self.thumbnail)
            image.verify()
        except Exception as exc:
            _log.warning(f"Topography {self.id} has no thumbnail. Reason: {exc}")
            return False
        return True

    @property
    def has_dzi(self):
        """If True, this topography is expected to have dzi data.

        For 1D topography data this is always False.
        """
        return (self.size_y is not None) and dzi_exists(self._dzi_storage_prefix())

    @property
    def storage_prefix(self):
        """Return prefix used for storage.

        Looks like a relative path to a directory.
        If storage is on filesystem, the prefix should correspond
        to a real directory.
        """
        if self.id is None:
            raise RuntimeError(
                "This `Topography` does not have an id yet; the storage prefix is not yet known."
            )
        return f"topographies/{self.id}"

    def get_related_surfaces(self):
        """Returns sequence of related surfaces.

        :return: True or False
        """
        return [self.surface]

    def get_absolute_url(self, request=None):
        """URL of API endpoint for this topography."""
        return reverse(
            "manager:topography-api-detail", kwargs=dict(pk=self.pk), request=request
        )

    def is_shared(self, with_user):
        """Returns True, if this topography is shared with a given user.

        Just returns whether the related surface is shared with the user
        or not.

        :param with_user: User to test
        :param allow_change: If True, only return True if topography can be changed by given user
        :return: True or False
        """
        return self.surface.is_shared(with_user)

    @staticmethod
    def _clean_instrument_parameters(params):
        cleaned_params = {}
        if params is None:
            return cleaned_params

        def _clean_value_unit_pair(r):
            cleaned_r = None
            if "value" in r and "unit" in r:
                # Value/unit pair is complete
                try:
                    cleaned_r = {"value": float(r["value"]), "unit": r["unit"]}
                except KeyError:
                    # 'value' or 'unit' does not exist - should not happen
                    pass
                except TypeError:
                    # Value is None
                    pass
                except ValueError:
                    # Value cannot be converted to float
                    pass
            return cleaned_r

        # Check completeness of resolution parameters
        for key in ["resolution", "tip_radius"]:
            try:
                r = _clean_value_unit_pair(params[key])
            except KeyError:
                pass
            else:
                if r is not None:
                    cleaned_params[key] = r

        return cleaned_params

    @property
    def _instrument_info(self):
        # We need to idiot-check the parameters JSON so surface topography does not complain
        # Would it be better to use JSON Schema for this? Or should we simply have dedicated database fields?
        params = self._clean_instrument_parameters(self.instrument_parameters)

        # Build dictionary with instrument information from database... this may override data provided by the
        # topography reader
        return {
            "instrument": {
                "name": self.instrument_name,
                "type": self.instrument_type,
                "parameters": params,
            }
        }

    def _read(self, reader):
        """Construct kwargs for reading topography given channel information"""
        if not _IN_CELERY_WORKER_PROCESS and self.size_y is not None:
            _log.warning(
                "You are requesting to load a (2D) topography and you are not within in a Celery worker "
                "process. This operation is potentially slow and may require a lot of memory - do not use "
                "`Topography.read` within the main Django server!"
            )

        reader_kwargs = dict(channel_index=self.data_source, periodic=self.is_periodic)

        channel = reader.channels[self.data_source]

        # Set size if physical size was not given in datafile
        # (see also  TopographyCreateWizard.get_form_initial)
        # Physical size is always a tuple or None.
        if channel.physical_sizes is None:
            if self.size_y is None:
                reader_kwargs["physical_sizes"] = (self.size_x,)
            else:
                reader_kwargs["physical_sizes"] = self.size_x, self.size_y

        if channel.height_scale_factor is None and self.height_scale:
            # Adjust height scale to value chosen by user
            reader_kwargs["height_scale_factor"] = self.height_scale

            # This is only possible and needed, if no height scale was given in the data file already.
            # So default is to use the factor from the file.

        # Set the unit, if not already given by file contents
        if channel.unit is None:
            reader_kwargs["unit"] = self.unit

        # Populate instrument information
        reader_kwargs["info"] = self._instrument_info

        # Eventually get topography from module "SurfaceTopography" using the given keywords
        topo = reader.topography(**reader_kwargs)
        if (
            self.fill_undefined_data_mode
            != Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING
            and topo.is_uniform
        ):
            topo = topo.interpolate_undefined_data(self.fill_undefined_data_mode)
        return topo.detrend(detrend_mode=self.detrend_mode)

    def read(self, allow_squeezed=True, return_reader=False):
        """Return a SurfaceTopography.Topography/UniformLineScan/NonuniformLineScan instance.

        This instance is guaranteed to

        - have a 'unit' property
        - have a size: .physical_sizes
        - have been scaled and detrended with the saved parameters

        It has not necessarily a pipeline with all these steps
        and a 'detrend_mode` attribute.

        This is only always the case
        if allow_squeezed=False. In this case the returned instance
        was regenerated from the original file with additional steps
        applied.

        If allow_squeezed=True, the returned topography may be read
        from a cached file which scaling and detrending already applied.

        Parameters
        ----------
        allow_squeezed: bool
            If True (default), the instance is allowed to be generated
            from a squeezed datafile which is not the original datafile.
            This is often faster than the original file format.

        return_reader: bool
            If True, return a tuple containing the topography and the reader.
            (Default: False)
        """
        #
        # Try to get topography from cache if possible
        #
        toporeader = None
        topo = None
        if allow_squeezed and self.has_squeezed_datafile:
            if not _IN_CELERY_WORKER_PROCESS and self.size_y is not None:
                _log.warning(
                    "You are requesting to load a (2D) topography and you are not within in a Celery worker "
                    "process. This operation is potentially slow and may require a lot of memory - do not use "
                    "`Topography.read` within the main Django server!"
                )

            # Okay, we can use the squeezed datafile, it's already there.
            toporeader = get_topography_reader(
                self.squeezed_datafile, format=SQUEEZED_DATAFILE_FORMAT
            )
            topo = toporeader.topography(info=self._instrument_info)
            # In the squeezed format, these things are already applied/included:
            # unit, scaling, detrending, physical sizes
            # so don't need to provide them to the .topography() method
            _log.info(
                f"Using squeezed datafile instead of original datafile for topography id {self.id}."
            )

        if topo is None:
            # Read raw file if squeezed file is unavailable
            toporeader = get_topography_reader(
                self.datafile, format=self.datafile_format
            )
            topo = self._read(toporeader)

        if return_reader:
            return topo, toporeader
        else:
            return topo

    topography = read  # Renaming this, mark `topography` as deprecated before v2

    def to_dict(self):
        """Create dictionary for export of metadata to json or yaml"""
        # FIXME!! This code should be moved to a separate serializer class
        result = {
            "name": self.name,
            "datafile": {
                "original": self.datafile.name,
                "squeezed-netcdf": self.squeezed_datafile.name,
            },
            "data_source": self.data_source,
            "has_undefined_data": self.has_undefined_data,
            "fill_undefined_data_mode": self.fill_undefined_data_mode,
            "detrend_mode": self.detrend_mode,
            "is_periodic": self.is_periodic,
            "creator": {"name": self.creator.name, "orcid": self.creator.orcid_id},
            "measurement_date": self.measurement_date,
            "description": self.description,
            "unit": self.unit,
            "size": (
                [self.size_x] if self.size_y is None else [self.size_x, self.size_y]
            ),
            "tags": [t.name for t in self.tags.order_by("name")],
            "instrument": {
                "name": self.instrument_name,
                "type": self.instrument_type,
                "parameters": self.instrument_parameters,
            },
        }
        if self.height_scale_editable:
            result["height_scale"] = self.height_scale
            # see GH 718

        return result

    def deepcopy(self, to_surface):
        """Creates a copy of this topography with all data files copied.

        Parameters
        ----------
        to_surface: Surface
            target surface

        Returns
        -------
        The copied topography.
        The reference to an instrument is not copied, it is always None.

        """

        copy = Topography.objects.get(pk=self.pk)
        copy.pk = None
        copy.task_id = None  # We need to indicate that no tasks have run
        copy.surface = to_surface

        # Set file names of derived data to None, otherwise they will be deleted and become unavailable to the
        # original topography
        copy.thumbnail = None
        copy.squeezed_datafile = None

        # Copy the actual data file
        with self.datafile.open(mode="rb") as datafile:
            copy.datafile = default_storage.save(self.datafile.name, File(datafile))

        copy.tags = self.tags.get_tag_list()

        # Recreate cache to recreate derived files
        _log.info(
            f"Creating cached properties of new {copy.get_subject_type()} {copy.id}..."
        )
        run_task(copy)
        copy.save()  # run_task sets the initial task state to 'pe', so we need to save

        return copy

    def get_thumbnail(self, width=400, height=400, cmap=None, st_topo=None):
        """
        Make thumbnail image.

        Parameters
        ----------
        width : int, optional
            Maximum width of the thumbnail. (Default: 400)
        height : int, optional
            Maximum height of the thumbnail. (Default: 400)
        cmap : str or colormap, optional
            Color map for rendering the topography. (Default: None)

        Returns
        -------
        image : bytes-like
            Thumbnail image.
        """
        if st_topo is None:
            st_topo = self.read()  # SurfaceTopography instance (=st)
        image_file = io.BytesIO()
        if st_topo.dim == 1:
            dpi = 100
            fig, ax = matplotlib.pyplot.subplots(figsize=[width / dpi, height / dpi])
            x, y = st_topo.positions_and_heights()
            ax.plot(x, y, "-")
            ax.set_axis_off()
            fig.savefig(image_file, bbox_inches="tight", dpi=100, format="png")
            matplotlib.pyplot.close(fig)  # probably saves memory, see issue 898
        elif st_topo.dim == 2:
            # Compute thumbnail size (keeping aspect ratio)
            sx, sy = st_topo.physical_sizes
            width2 = int(sx * height / sy)
            height2 = int(sy * width / sx)
            if width2 <= width:
                width = width2
            else:
                height = height2

            # Get heights and rescale to interval 0, 1
            heights = st_topo.heights()
            mx, mn = heights.max(), heights.min()
            heights = (heights - mn) / (mx - mn)
            # Get color map
            cmap = matplotlib.pyplot.get_cmap(cmap)
            # Convert to image
            colors = (cmap(heights.T) * 255).astype(np.uint8)
            # Remove alpha channel before writing
            PIL.Image.fromarray(colors[:, :, :3]).resize((width, height)).save(
                image_file, format="png"
            )
        else:
            raise RuntimeError(
                f"Don't know how to create thumbnail for topography of dimension {st_topo.dim}."
            )
        return image_file

    def _renew_thumbnail(self, st_topo=None):
        """Renews thumbnail.

        Returns
        -------
        None
        """
        if st_topo is None:
            st_topo = self.read()

        image_file = self.get_thumbnail(st_topo=st_topo)

        # Remove old thumbnail
        self.thumbnail.delete()

        # Save the contents of in-memory file in Django image field
        self.thumbnail.save(
            "thumbnail.png", ContentFile(image_file.getvalue()), save=False
        )  # Do NOT trigger a model save

    def _dzi_storage_prefix(self):
        """Return prefix for storing DZI images."""
        return f"{self.storage_prefix}/dzi"

    def _renew_dzi(self, st_topo=None):
        """Renew deep zoom images.

        Returns
        -------
        None
        """
        if st_topo is None:
            st_topo = self.read()
        if self.size_y is not None:
            # This is a topography (map), we need to create a Deep Zoom Image
            make_dzi(st_topo, self._dzi_storage_prefix())

    def renew_thumbnail(self, none_on_error=True, st_topo=None):
        """Renew thumbnail field.

        Parameters
        ----------
        none_on_error: bool
            If True (default), sets thumbnail to None if there are any errors.
            If False, exceptions have to be caught outside.

        Returns
        -------
        None

        Raises
        ------
        ThumbnailGenerationException
        """
        try:
            self._renew_thumbnail(st_topo=st_topo)
        except Exception as exc:
            if none_on_error:
                self.thumbnail = None
                self.save()
                _log.warning(
                    f"Problems while generating thumbnail for topography {self.id}: {exc}. "
                    "Saving <None> instead."
                )
                import traceback

                _log.warning(f"Traceback: {traceback.format_exc()}")
            else:
                raise ThumbnailGenerationException(self, str(exc)) from exc

    def renew_dzi(self, none_on_error=True, st_topo=None):
        """Renew deep zoom image files.

        Parameters
        ----------
        none_on_error: bool
            If True (default), do not raise an exception if there are any errors.
            If False, exceptions have to be caught outside.

        Returns
        -------
        None

        Raises
        ------
        DZIGenerationException
        """
        try:
            self._renew_dzi(st_topo=st_topo)
        except Exception as exc:
            if none_on_error:
                _log.warning(
                    f"Problems while generating deep zoom images for topography {self.id}: {exc}."
                )
                import traceback

                _log.warning(f"Traceback: {traceback.format_exc()}")
            else:
                raise DZIGenerationException(self, str(exc)) from exc

    def renew_squeezed_datafile(self, st_topo=None):
        if st_topo is None:
            st_topo = self.read()
        with tempfile.NamedTemporaryFile() as tmp:
            # Write and upload NetCDF file
            st_topo.to_netcdf(tmp.name)
            # Delete old squeezed file
            self.squeezed_datafile.delete()
            # Upload new squeezed file
            dirname, basename = os.path.split(self.datafile.name)
            orig_stem, orig_ext = os.path.splitext(basename)
            squeezed_name = f"{orig_stem}-squeezed.nc"
            self.squeezed_datafile.save(
                squeezed_name, File(open(tmp.name, mode="rb")), save=False
            )  # Do NOT trigger a model save

    def renew_bandwidth_cache(self, st_topo=None):
        """Renew bandwidth cache.

        Cache bandwidth for bandwidth plot in database. Data is stored in units of meter.
        """
        if st_topo is None:
            st_topo = self.read()
        if st_topo.unit is not None:
            bandwidth_lower, bandwidth_upper = st_topo.bandwidth()
            fac = get_unit_conversion_factor(st_topo.unit, "m")
            self.bandwidth_lower = fac * bandwidth_lower
            self.bandwidth_upper = fac * bandwidth_upper

            try:
                short_reliability_cutoff = (
                    st_topo.short_reliability_cutoff()
                )  # Return float or None
            except UndefinedDataError:
                # Short reliability cutoff can only be computed on topographies without undefined data
                short_reliability_cutoff = None
            if short_reliability_cutoff is not None:
                short_reliability_cutoff *= fac
            self.short_reliability_cutoff = (
                short_reliability_cutoff  # None is also saved here
            )

    @property
    def is_metadata_complete(self):
        """Check whether we have all metadata to actually read the file"""
        return (
            self.size_x is not None
            and self.unit is not None
            and self.height_scale is not None
        )

    def notify_users_with_perms(self, verb, description):
        other_users = get_users_with_perms(self.surface).filter(
            ~models.Q(id=self.creator.id)
        )
        for u in other_users:
            notify.send(
                sender=self.creator, recipient=u, verb=verb, description=description
            )

    def renew_cache(self):
        """
        Inspect datafile and renew cached properties, in particular database entries on resolution, size etc. and the
        squeezed NetCDF representation of the data.
        """
        # First check if we have a datafile
        if not self.datafile:
            # No datafile; this may mean a datafile has been uploaded to S3
            file_path = topography_datafile_path(
                self, self.name
            )  # name and filename are identical at this point
            if not default_storage.exists(file_path):
                raise RuntimeError(
                    f"Topography {self.id} does not appear to have a data file (expected at path "
                    f"'{file_path}')."
                )
            _log.info(f"Found newly uploaded file: {file_path}")
            # Data file exists; path the datafile field to point to the correct file
            self.datafile.name = file_path
            # Notify users that a new file has been uploaded
            self.notify_users_with_perms(
                "create",
                f"User '{self.creator}' uploaded the measurement '{self.name}' to "
                f"digital surface twin '{self.surface.name}'.",
            )

        # Check if this is the first time we are opening this file...
        populate_initial_metadata = self.data_source is None

        # Populate datafile information in the database.
        # (We never load the topography, so we don't know this until here.
        # Fields that are undefined are autodetected.)
        _log.info(f"Caching properties of topography {self.id}...")

        # Open topography file
        reader = get_topography_reader(self.datafile)
        self.datafile_format = reader.format()

        # Update channel names
        self.channel_names = [
            (channel.name, _get_unit(channel)) for channel in reader.channels
        ]

        # Idiot check
        if len(self.channel_names) == 0:
            raise RuntimeError(
                "Datafile could be opened, but it appears to contain no valid data."
            )

        # Check whether the user already selected a (valid) channel, if not set to default channel
        if (
            self.data_source is None
            or self.data_source < 0
            or self.data_source >= len(self.channel_names)
        ):
            self.data_source = reader.default_channel.index

        # Select channel
        channel = reader.channels[self.data_source]

        #
        # Look for necessary metadata. We override values in the database. This may be necessary if the underlying
        # reader changes (e.g. through bug fixes).
        #

        # Populate resolution information in the database
        if channel.dim == 1:
            (self.resolution_x,) = channel.nb_grid_pts
            self.resolution_y = None  # This indicates that this is a line scan
        elif channel.dim == 2:
            self.resolution_x, self.resolution_y = channel.nb_grid_pts
        else:
            raise NotImplementedError(
                f"Cannot handle topographies of dimension {channel.dim}."
            )

        # Populate size information in the database
        if channel.physical_sizes is None:
            # Data file *does not* provide size information; the user must provide it
            self.size_editable = True
        else:
            # Data file *does* provide size information; the user cannot override it
            self.size_editable = False
            # Reset size information here
            if channel.dim == 1:
                (self.size_x,) = channel.physical_sizes
                self.size_y = None
            elif channel.dim == 2:
                self.size_x, self.size_y = channel.physical_sizes
            else:
                raise NotImplementedError(
                    f"Cannot handle topographies of dimension {channel.dim}."
                )

        # Populate unit information in the database
        if channel.unit is None:
            # Data file *does not* provide unit information; the user must provide it
            self.unit_editable = True
        else:
            # Data file *does* provide unit information; the user cannot override it
            self.unit_editable = False
            # Reset unit information here
            if isinstance(channel.unit, tuple):
                raise NotImplementedError(
                    f"Data channel '{channel.name}' contains information that is not height."
                )
            self.unit = channel.unit

        # Populate height scale information in the database
        if channel.height_scale_factor is None:
            # Data file *does not* provide height scale information; the user must provide it
            self.height_scale_editable = True
        else:
            # Data file *does* provide height scale information; the user cannot override it
            self.height_scale_editable = False
            # Reset unit information here
            self.height_scale = channel.height_scale_factor

        # Populate information on periodicity
        if not channel.is_uniform:
            # This is a nonuniform line scan that does not support periodicity
            self.is_periodic_editable = False
            self.is_periodic = False
        elif self.is_periodic is None:
            # This is a uniform line scan or map, periodicity is supported
            self.is_periodic_editable = True
            self.is_periodic = channel.is_periodic

        #
        # We now look for optional metadata. Only import it from the file on first read, otherwise we may override
        # what the user has painfully adjusted when refreshing the cache.
        #

        if populate_initial_metadata:
            # Measurement time
            try:
                self.measurement_date = dateutil.parser.parse(
                    channel.info["acquisition_time"]
                )
            except:  # noqa: E722
                pass

            # Instrument name
            try:
                self.instrument_name = channel.info["instrument"]["name"]
            except:  # noqa: E722
                pass

            # Instrument parameters
            try:
                self.instrument_parameters = channel.info["instrument"]["parameters"]
                if "tip_radius" in self.instrument_parameters:
                    self.instrument_type = self.INSTRUMENT_TYPE_CONTACT_BASED
                elif "resolution" in self.instrument_parameters:
                    self.instrument_type = self.INSTRUMENT_TYPE_MICROSCOPE_BASED
            except:  # noqa: E722
                self.instrument_type = self.INSTRUMENT_TYPE_UNDEFINED

        # Read the file if metadata information is complete
        if self.is_metadata_complete:
            _log.info(f"Metadata of {self} is complete. Generating images.")
            st_topo = self._read(reader)

            # Check whether original data file has undefined data point and update database accordingly.
            # (`has_undefined_data` can be undefined if undetermined.)
            self.has_undefined_data = st_topo.has_undefined_data

            # Refresh other cached quantities
            self.renew_bandwidth_cache(st_topo=st_topo)
            self.renew_thumbnail(st_topo=st_topo)
            self.renew_dzi(st_topo=st_topo)
            self.renew_squeezed_datafile(st_topo=st_topo)

        # Save dataset
        self.save()

        # Send signal
        _log.debug(f"Sending `post_renew_cache` signal from {self}...")
        post_renew_cache.send(sender=Topography, instance=self)

    def get_undefined_data_status(self):
        """Get human-readable description about status of undefined data as string."""
        s = self.HAS_UNDEFINED_DATA_DESCRIPTION[self.has_undefined_data]
        if (
            self.fill_undefined_data_mode
            == Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING
        ):
            s += " No correction of undefined data is performed."
        elif (
            self.fill_undefined_data_mode
            == Topography.FILL_UNDEFINED_DATA_MODE_HARMONIC
        ):
            s += " Undefined/missing values are filled in with values obtained from a harmonic interpolation."
        return s

    def task_worker(self):
        self.renew_cache()


class FileParent(models.Model):
    surface = models.OneToOneField(
        Surface, on_delete=models.CASCADE, null=True, blank=True
    )
    topography = models.OneToOneField(
        Topography, on_delete=models.CASCADE, null=True, blank=True
    )

    def get_owner(self) -> tuple[str, Union[Surface, Topography]]:
        for field in self._meta.fields:
            if field.is_relation and (fk := getattr(self, field.name)) is not None:
                return (field.name, fk)
        raise ValueError("Exactly one field has to be not null")

    def validate(self):
        """
        Checks the invariants of this Model.
        If any invariant is broken, a ValidationError is raised

        Invariants:
        - 1. `surface` or `topography` are `None`
        - 2. `surface` or `topography` are not `None`
        This results in a 'XOR' logic and exaclty one of the value fields has to hold a value
        """

        # Invariant 1
        if not (self.surface is None or self.topography is None):
            raise ValidationError("Either 'surface' or 'topography' must be None.")
        # Invariant 2
        if not (self.surface is not None or self.topography is not None):
            raise ValidationError("Either 'surface' or 'topography' must be not None.")

    def save(self, *args, **kwargs):
        self.validate()
        super().save(*args, **kwargs)

    def get_valid_files(self) -> models.QuerySet["FileManifest"]:
        # NOTE: "files" is the reverse `related_name` for the relation to `FileManifest`
        return self.files.filter(upload_finished__isnull=False)

    def __str__(self) -> str:
        owner_type, owner_obj = self.get_owner()
        return f"FileParent : {owner_type} - {owner_obj}"


# The Flow for "direct file upload" is heavily inspired from here:
# https://www.hacksoft.io/blog/direct-to-s3-file-upload-with-django
class FileManifest(models.Model):
    FILE_KIND_CHOICES = [("att", "Attachment"), ("raw", "Raw data file")]

    file = models.FileField(upload_to=generate_upload_path, blank=True, null=True)

    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=255, blank=True, null=True)

    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)

    parent = models.ForeignKey(
        FileParent, related_name="files", on_delete=models.CASCADE
    )
    kind = models.CharField(max_length=3, choices=FILE_KIND_CHOICES)

    upload_finished = models.DateTimeField(blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"FileManifest:\n\tfile -> {self.file}\n\tparent -> {self.parent}\n\tkind -> {self.kind}"

    def delete(self, *args, **kwargs):
        self.file.delete(save=False)
        return super().delete(*args, **kwargs)

    @property
    def is_valid(self):
        return bool(self.upload_finished)

    @property
    def url(self):
        return self.file.url
