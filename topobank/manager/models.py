"""
Basic models for the web app for handling topography data.
"""

import itertools
import logging
from collections import defaultdict
from typing import List

import django.dispatch
import numpy as np
import pydantic
import tagulous.models as tm
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.core.exceptions import PermissionDenied
from django.core.files import File
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q, Value
from django.utils import timezone
from SurfaceTopography.Container.SurfaceContainer import SurfaceContainer
from SurfaceTopography.Exceptions import UndefinedDataError
from SurfaceTopography.IO import ReaderBase
from SurfaceTopography.Support.UnitConversion import get_unit_conversion_factor

from ..authorization import get_permission_model
from ..authorization.mixins import PermissionMixin
from ..authorization.models import (
    AuthorizedManager,
    SurfaceTopographyManager,
    ViewEditFull,
)
from ..files.models import Manifest, ManifestSet
from ..taskapp.models import IncompleteMetadataError, TaskStateModel
from ..taskapp.utils import run_task
from ..measurements.registry import (
    MeasurementNotInspectedError,
    MeasurementRegistryError,
    get_adapter,
    has_adapter,
    infer_kind,
)
from ..measurements.adapters import (
    write_canonical_manifest,
    write_thumbnail_manifest,
)
from ..measurements.schemas import dump_metadata, significant_values
from ..utils.timer import Timer
from .utils import get_topography_reader

_log = logging.getLogger(__name__)

pre_refresh_cache = django.dispatch.Signal()
post_refresh_cache = django.dispatch.Signal()

MAX_LENGTH_DATAFILE_FORMAT = (
    15  # some more characters than currently needed, we may have sub formats in future
)
SQUEEZED_DATAFILE_FORMAT = "nc"


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


class SqueezedDatafileGenerationException(ThumbnailGenerationException):
    """Failure while generating squeezed data files for a topography."""

    pass


class TopobankLazySurfaceContainer(SurfaceContainer):
    """Wraps a `Surface` with lazy loading of topography data"""

    def __init__(self, surface, **kwargs):
        self._surface = surface
        self._topographies = self._surface.measurements.all()
        self._kwargs = kwargs

    def __len__(self):
        return len(self._topographies)

    def __getitem__(self, item):
        return self._topographies[item].read(**self._kwargs)


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

    def is_shared(self, user) -> bool:
        """Returns True, if this subject is shared with a given user.

        Always returns True if user is the creator of the related surface.

        :param user: User to test
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


class Tag(tm.TagTreeModel, SubjectMixin):
    """This is the common tag model for surfaces and topographies."""

    _user = None

    # TODO: Make this work with permission mixin
    def authorize_user(
        self,
        user=None,
        access_level: ViewEditFull = "view",
        permissions=None,
    ):
        if access_level != "view":
            raise PermissionDenied(
                f"Cannot elevate permission to '{access_level}' because tags are not "
                "editable."
            )
        if user is not None:
            if permissions is not None:
                raise RuntimeError(
                    "Can authorize with either user name or permission set, not both."
                )
            self._user = user
        elif permissions is not None:
            users = permissions.get_users()
            if len(users) == 0:
                raise RuntimeError(
                    "Trying to authorize with permission set that has no users."
                )
            elif len(users) > 1:
                raise PermissionError(
                    "Trying to authorize with permission set with more than one user."
                )
            self._user, _ = users[0]
        else:
            raise RuntimeError("Need user name or permission set to authorize.")

    def is_shared(self, user) -> bool:
        return True  # Tags are generally shared, but the surfaces may not

    def get_authorized_user(self):
        return self._user

    def get_related_surfaces(self):
        """Return all surfaces with exactly this tag"""
        if self._user is None:
            raise PermissionError(
                "Cannot return surfaces belonging to a tag because "
                "no user was specified. Use `authorize_user` "
                "to restrict user permissions."
            )
        return Surface.objects.for_user(self._user).filter(tags=self.id)

    def get_children(self) -> List[str]:
        def make_child(tag_name):
            tag_suffix = tag_name[len(self.name) + 1:]
            name, rest = (tag_suffix + "/").split("/", maxsplit=1)
            return f"{self.name}/{name}"

        if self._user is None:
            raise PermissionError(
                "Cannot return children of a tag because "
                "no user was specified. Use `authorize_user` "
                "to restrict user permissions."
            )
        all_tags = set(
            itertools.chain.from_iterable(
                Surface.objects.for_user(self._user)
                .filter(tags__name__startswith=f"{self.name}/")
                .values_list("tags__name")
            )
        )
        return list(
            set(make_child(tag) for tag in all_tags if tag.startswith(f"{self.name}/"))
        )

    def get_descendant_surfaces(self):
        """Return all surfaces with exactly this tag or a descendant tag"""
        if self._user is None:
            raise PermissionError(
                "Cannot return surfaces belonging to a tag because "
                "no user was specified. Use `authorize_user` "
                "to restrict user permissions."
            )
        return (
            Surface.objects.for_user(self._user)
            .filter(Q(tags=self) | Q(tags__path__istartswith=f"{self.path}/"))
            .distinct()
        )

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

        nb_surfaces = len(self.get_descendant_surfaces())

        # Initialize a dictionary to collect all properties. The default value for
        # each property is a list of np.nan of length equal to the number of
        # surfaces.
        property_values = defaultdict(lambda: [np.nan] * nb_surfaces)
        categorical_properties = set()

        # Iterate over all surfaces related to the tag
        for i, surface in enumerate(self.get_descendant_surfaces()):
            # For each surface, iterate over all its properties
            for p in surface.properties.all():
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


def flatten_for_search(s):
    """Prepare a name for full-text search.

    Replaces the separators '.' and '/' (common in file names and hierarchical
    tag names) with spaces so that the tokenizer splits them into words.
    """
    if s is None:
        return ""
    return s.replace(".", " ").replace("/", " ")


class Surface(PermissionMixin, models.Model, SubjectMixin):
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

    class Meta:
        ordering = ["name"]
        indexes = [
            # Index on name for ordering in list views
            models.Index(fields=['name'], name='surface_name_idx'),
            # Composite index for filtering and ordering
            # Used in: list queries with deleted_at filter
            models.Index(fields=['deleted_at', 'name'], name='surface_list_idx'),
            # Partial index for active (non-deleted) surfaces
            # Most common query: only show surfaces where deleted_at IS NULL
            # More efficient than full index since it excludes soft-deleted rows
            models.Index(
                fields=['name'],
                name='surface_active_name_idx',
                condition=Q(deleted_at__isnull=True)
            ),
            # Full-text search over the precomputed search document
            GinIndex(fields=['search_vector'], name='surface_search_idx'),
        ]

    #
    # Manager
    # Automatically filter out deleted surfaces in the default manager.
    #
    objects = SurfaceTopographyManager()
    #
    # We need to have a separate manager for all_objects, because the default manager is used for related fields,
    # and we don't want to include deleted objects there. The all_objects manager can be used for admin views and
    # for the lazy deletion mechanism.
    #
    all_objects = AuthorizedManager()

    #
    # Permissions
    #
    permissions = models.ForeignKey(
        getattr(settings, 'TOPOBANK_PERMISSION_MODEL', 'authorization.PermissionSet'),
        on_delete=models.CASCADE, null=True
    )

    #
    # Ownership
    #

    # `created_by` is only NULL if user is deleted after dataset has been created.
    # Custodian should NOT remove datasets with NULL created_by
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    # User who soft-deleted this dataset. NULL when it is not deleted, when the
    # deletion was a system operation, or for datasets deleted before this field
    # existed. Only meaningful while `deleted_at` is set.
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        blank=True, related_name="+"
    )

    # `owned_by` is always an organization. The field is only NULL if
    # organization is deleted after dataset has been created.
    # Custodian should remove all datasets with NULL organization.
    owned_by = models.ForeignKey(
        getattr(settings, 'TOPOBANK_ORGANIZATION_MODEL', 'organizations.Organization'),
        on_delete=models.SET_NULL, null=True
    )

    #
    # Dataset metadata
    #
    name = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    category = models.CharField(
        max_length=3, choices=CATEGORY_CHOICES, null=True, blank=False
    )
    tags = tm.TagField(to=Tag)

    #
    # Full-text search: precomputed search document (see
    # `update_search_vector`), kept up to date by signal handlers in
    # `signals.py` and queried through a GIN index.
    #
    search_vector = SearchVectorField(null=True, editable=False)

    #
    # Time stamps
    #
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)
    # If deletion date is set, the datasets will be deleted after TOPOBANK_DELETE_DELAY
    deleted_at = models.DateTimeField(null=True)

    #
    # Attachments
    #
    attachments = models.ForeignKey(ManifestSet, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        s = f"Dataset '{self.name}'"
        if self.is_published:
            s += f" (version {self.publication.version})"
        return s

    @property
    def label(self):
        s = self.name
        if self.is_published:
            s += f" (version {self.publication.version})"
        return s

    def get_related_surfaces(self):
        return [self]

    def num_measurements(self):
        return self.measurements.count()

    def save(self, *args, **kwargs):
        created = self.pk is None
        if created:
            if self.permissions is None:
                # Create a new permission set for this dataset
                _log.debug(
                    f"NEW DATASET: Creating an empty permission set for dataset {self}."
                )
                self.permissions = get_permission_model().objects.create()
            # Grant permissions to created_by
            self.permissions.grant_for_user(self.created_by, "full")
        if self.attachments is None:
            # Create a new folder for attachments
            _log.debug(
                "ATTACHMENTS MISSING: Creating an empty folder for attachments to "
                f"{self}."
            )
            self.attachments = ManifestSet.objects.create(
                permissions=self.permissions, read_only=False
            )
        super().save(*args, **kwargs)

    def lazy_delete(self, deleted_by=None):
        """Mark this dataset and its measurements for deletion.

        `deleted_by` is the user performing the deletion, recorded on both this
        dataset and the measurements this call cascades to. Pass None for system
        operations.
        """
        self.deleted_at = timezone.now()
        self.deleted_by = deleted_by
        self.save(update_fields=["deleted_at", "deleted_by"])
        self.measurements.filter(deleted_at__isnull=True).update(
            deleted_at=self.deleted_at, deleted_by=deleted_by
        )

    def build_search_document(self):
        """Assemble the plain-text document used for full-text search.

        Combines the dataset's own name, description, creator and tags with
        those of its measurements. Separators in file and hierarchical tag
        names are flattened so the tokenizer splits them into words.
        """
        parts = [
            flatten_for_search(self.name),
            self.description or "",
            self.created_by.name if self.created_by is not None else "",
        ]
        parts += [flatten_for_search(tag.name) for tag in self.tags.all()]
        for topography in self.measurements.select_related("created_by").prefetch_related("tags").all():
            parts += [
                flatten_for_search(topography.name),
                topography.description or "",
                (
                    topography.created_by.name
                    if topography.created_by is not None
                    else ""
                ),
            ]
            parts += [
                flatten_for_search(tag.name) for tag in topography.tags.all()
            ]
        return " ".join(part for part in parts if part)

    def update_search_vector(self):
        """Recompute and store the full-text search vector for this dataset.

        This is the single place where the search document is written. It uses
        a queryset update to avoid recursive `save` calls and signals.
        """
        if self.pk is None:
            return
        Surface.all_objects.filter(pk=self.pk).update(
            search_vector=SearchVector(
                Value(self.build_search_document()), config="english"
            )
        )

    def to_dict(self):
        """Create dictionary for export of metadata to json or yaml.

        Does not include topographies. They can be added like this:

         surface_dict = surface.to_dict()
         surface_dict['topographies'] = [t.to_dict() for t in surface.measurements.order_by('name')]

        The publication URL will be based on the official contact.engineering URL.

        Returns:
            dict
        """
        created_by = {"name": self.created_by.name}
        orcid = getattr(self.created_by, 'orcid_id', None)
        if orcid is not None:
            created_by["orcid"] = orcid
        d = {
            "name": self.name,
            "category": self.category,
            "created_by": created_by,
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

    def is_shared(self, user) -> bool:
        """
        Returns True if this surface is shared with a given user.

        Always returns True if the user is the creator of the surface.
        """
        return self.get_permission(user) is not None

    def grant_permission(self, principal, allow: ViewEditFull = "view"):
        # This is an additional guard: Published datasets have empty permission sets
        if self.is_published:
            raise PermissionDenied(
                "Permissions of a published dataset cannot be changed."
            )

        super().grant_permission(principal, allow)

    def revoke_permission(self, principal):
        # This is an additional guard: Published datasets have empty permission sets
        if self.is_published:
            raise PermissionDenied(
                "Permissions of a published dataset cannot be changed."
            )

        super().revoke_permission(principal)

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
        surface.permissions = None  # Will be autogenerated on save
        surface.task_id = None  # We need to indicate that no tasks have run
        surface.tags = self.tags.get_tag_list()
        surface.save()  # This will create a new PermissionSet
        surface.attachments = self.attachments.deepcopy(permissions=surface.permissions)
        surface.save(update_fields=["attachments"])

        for topography in self.measurements.all():
            topography.deepcopy(surface)
            # we pass the surface here because there is a constraint that (surface_id +
            # topography name) must be unique, i.e. a surface should never have two
            # topographies of the same name, so we can't set the new surface as the
            # second step
        for property in self.properties.all():
            property.deepcopy(surface)

        _log.info("Created deepcopy of surface %s -> surface %s", self.pk, surface.pk)
        return surface

    @property
    def is_published(self):
        """Returns True, if a publication for this surface exists."""
        return hasattr(
            self, "publication"
        )  # checks whether the related object surface.publication exists

    def lazy_read(self, **kwargs):
        """
        Returns a `SurfaceTopography.Container.SurfaceContainer`
        representation of this dataset. Reading of actual data is deferred
        to the point where it is actually needed.
        """
        return TopobankLazySurfaceContainer(self, **kwargs)


class Measurement(PermissionMixin, TaskStateModel, SubjectMixin):
    """
    A single measurement of a surface of a specimen.

    Presently every measurement holds topography (height) data; the name is
    deliberately generic because the model itself carries only identity,
    permissions, files and task state.
    """

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

    class Meta:
        ordering = ["measurement_date", "pk"]
        unique_together = (("surface", "name"),)
        verbose_name = "measurement"
        verbose_name_plural = "measurements"
        indexes = [
            # Index on surface foreign key for JOIN optimization
            # Used in: surface.measurements.all() and filtering by surface__deleted_at
            models.Index(fields=['surface'], name='topography_surface_idx'),
            # Composite index for filtering and ordering
            # Used in: list queries with deleted_at filter
            models.Index(fields=['deleted_at', 'name'], name='topography_list_idx'),
            # Partial index for active (non-deleted) topographies
            # Most common query: only show topographies where deleted_at IS NULL
            # More efficient than full index since it excludes soft-deleted rows
            models.Index(
                fields=['name'],
                name='topography_active_name_idx',
                condition=Q(deleted_at__isnull=True)
            ),
        ]

    #
    # Manager
    #
    # Automatically filter out deleted topographies in the default manager.
    #
    objects = SurfaceTopographyManager()
    #
    # We need to have a separate manager for all_objects, because the default manager is used for related fields,
    # and we don't want to include deleted objects there. The all_objects manager can be used for admin views and
    # for the lazy deletion mechanism.
    #
    all_objects = AuthorizedManager()
    #
    # Model hierarchy and permissions
    #
    permissions = models.ForeignKey(
        getattr(settings, 'TOPOBANK_PERMISSION_MODEL', 'authorization.PermissionSet'),
        on_delete=models.CASCADE, null=True
    )
    surface = models.ForeignKey(
        Surface, on_delete=models.CASCADE, related_name="measurements"
    )

    #
    # Descriptive fields
    #
    name = models.TextField()  # This must be identical to the file name on upload
    #
    # User who created this topography
    #
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    #
    # User who last updated this topography (no reverse lookup needed)
    #
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    #
    # User who soft-deleted this measurement, either directly or via a cascade
    # from its dataset. NULL for system operations and for measurements deleted
    # before this field existed. Only meaningful while `deleted_at` is set.
    #
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+"
    )
    #
    # Organization owning this topography. (Cleanup only happens if the surface is deleted)
    #
    owned_by = models.ForeignKey(
        getattr(settings, "TOPOBANK_ORGANIZATION_MODEL", "organizations.Organization"),
        null=True,
        on_delete=models.SET_NULL,
    )
    measurement_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)
    tags = tm.TagField(to=Tag)
    attachments = models.ForeignKey(ManifestSet, on_delete=models.SET_NULL, null=True)

    #
    # Time stamps
    #
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)
    # If deletion date is set, the datasets will be deleted after TOPOBANK_DELETE_DELAY
    deleted_at = models.DateTimeField(null=True)

    #
    # Fields related to raw data
    #
    datafile = models.ForeignKey(
        Manifest,
        null=True,
        on_delete=models.SET_NULL,
        related_name="topography_datafiles",
    )
    datafile_format = models.CharField(
        max_length=MAX_LENGTH_DATAFILE_FORMAT, null=True, default=None, blank=True
    )
    channel_names = models.JSONField(default=list)
    data_source = models.IntegerField(null=True)  # Channel index

    #
    # Kind of measurement
    #
    # Registry key of the measurement adapter that handles this record; see
    # `topobank.measurements`. Null until the data file has been inspected, since
    # the kind is derived from the selected channel. A value with no registered
    # type means the plugin that created the measurement is not installed: the
    # record stays listable, downloadable and deletable, but its data cannot be
    # read.
    kind = models.TextField(null=True, blank=True, editable=False)

    #
    # Metadata
    #
    # User-facing physical metadata, validated against the schema of this
    # measurement's kind (see `topobank.measurements.schemas`). Reached through
    # `meta`, which parses it, rather than read as a raw dict.
    metadata = models.JSONField(default=dict)
    # Read-only cache derived from the data file, written only by the inspection
    # task. Reached through `info`.
    file_info = models.JSONField(default=dict)
    # Django documentation discourages the use of null=True on a CharField. We use it
    # here nevertheless, because we need this values as argument to a function where
    # None has a special meaning (autodetection of format). If we used an empty string
    # as proposed in the docs, we would need extra logic everywhere the field
    # 'datafile_format' is used.

    # All data is also stored in a standardized and "squeezed" (all filters, e.g.
    # scaling and detrending, applied) format for faster loading and processing. This
    # file is a netCDF3 file.
    squeezed_datafile = models.ForeignKey(
        Manifest,
        null=True,
        on_delete=models.SET_NULL,
        related_name="topography_squeezed_datafiles",
    )

    #
    # Fields with physical meta data
    #
    #
    # Legacy metadata columns
    #
    # Superseded by `metadata` and `file_info`, which `0090` filled in from these.
    # Kept only so a backfill found to be wrong can be re-run from the original
    # data, and renamed so that a reader nobody noticed raises `AttributeError`
    # instead of quietly returning a pre-migration value. Nothing should read
    # these; `0092` drops them.
    #
    legacy_size_editable = models.BooleanField(default=False, editable=False)
    legacy_size_x = models.FloatField(null=True, validators=[MinValueValidator(0.0)])
    legacy_size_y = models.FloatField(
        null=True, validators=[MinValueValidator(0.0)]
    )  # null for line scans

    legacy_unit_editable = models.BooleanField(default=False, editable=False)
    legacy_unit = models.TextField(choices=LENGTH_UNIT_CHOICES, null=True)

    legacy_height_scale_editable = models.BooleanField(default=False, editable=False)
    legacy_height_scale = models.FloatField(default=1)

    legacy_has_undefined_data = models.BooleanField(
        null=True, default=None
    )  # default is undefined
    # Fraction (not percentage) of the data points of the measured data that are
    # undefined, in [0, 1]. Null until the measurement has been inspected.
    legacy_undefined_data_fraction = models.FloatField(
        null=True, default=None, editable=False
    )
    legacy_fill_undefined_data_mode = models.TextField(
        choices=FILL_UNDEFINED_DATA_MODE_CHOICES,
        default=FILL_UNDEFINED_DATA_MODE_NOFILLING,
    )

    legacy_detrend_mode = models.TextField(choices=DETREND_MODE_CHOICES, default="center")
    # The trend that was subtracted, as `slope_x`/`slope_y` (dimensionless) and
    # `radius_x`/`radius_y` (in `unit`); see `utils.detrend_parameters`. Null until
    # the measurement has been inspected, empty when the mode fits no trend.
    legacy_detrend_parameters = models.JSONField(null=True, default=None, editable=False)

    legacy_resolution_x = models.IntegerField(
        null=True, editable=False, validators=[MinValueValidator(0)]
    )  # null for line scans
    legacy_resolution_y = models.IntegerField(
        null=True, editable=False, validators=[MinValueValidator(0)]
    )  # null for line scans

    legacy_bandwidth_lower = models.FloatField(
        null=True, default=None, editable=False
    )  # in meters
    legacy_bandwidth_upper = models.FloatField(
        null=True, default=None, editable=False
    )  # in meters
    legacy_short_reliability_cutoff = models.FloatField(
        null=True, default=None, editable=False
    )

    legacy_is_periodic_editable = models.BooleanField(default=True, editable=False)
    legacy_is_periodic = models.BooleanField(default=False)

    #
    # Fields about instrument and its parameters
    #
    legacy_instrument_name = models.CharField(max_length=200, blank=True)
    legacy_instrument_type = models.TextField(
        choices=INSTRUMENT_TYPE_CHOICES, default=INSTRUMENT_TYPE_UNDEFINED
    )
    legacy_instrument_parameters = models.JSONField(default=dict)

    #
    # Thumnbnail and deep zoom files
    #
    thumbnail = models.ForeignKey(
        Manifest,
        null=True,
        on_delete=models.SET_NULL,
        related_name="topography_thumbnails",
    )
    deepzoom = models.ForeignKey(
        ManifestSet,
        null=True,
        on_delete=models.SET_NULL,
        related_name="topography_deepzooms",
    )

    #
    # Methods
    #
    def save(self, *args, **kwargs):
        update_fields: list = kwargs.get("update_fields", None)
        created = self.pk is None
        if created:
            if self.permissions is None:
                _log.debug(
                    f"NEW TOPOGRAPHY: Attaching topography to surface permissions {self}."
                )
                if self.surface.permissions is not None:
                    self.permissions = self.surface.permissions
                else:
                    raise RuntimeError(
                        "Cannot create topography because surface has no permissions."
                    )
        if self.attachments is None:
            _log.debug(
                "ATTACHMENTS MISSING: Creating an empty folder for attachments to "
                f"{self}."
            )
            self.attachments = ManifestSet.objects.create(
                permissions=self.permissions, read_only=False
            )
            if update_fields is not None and 'attachments' not in update_fields:
                update_fields.append('attachments')
        if self.datafile is None:
            _log.debug(
                f"DATAFILE MISSING: Creating datafile manifest for Measurement: {self}")
            self.datafile = Manifest.objects.create(
                permissions=self.permissions,
                filename=self.name,
                kind="raw",
                created_by=self.created_by
            )
            if update_fields is not None and 'datafile' not in update_fields:
                update_fields.append('datafile')

        # Reset to no refresh
        refresh_dependent_data = False

        # Strategies to detect changes in significant fields:
        # https://stackoverflow.com/questions/1355150/when-saving-how-can-you-check-if-a-field-has-changed
        try:
            # Do not check for None in self.id as this breaks should we switch to UUIDs
            old_obj = Measurement.objects.get(pk=self.pk)
        except self.DoesNotExist:
            pass  # Do nothing, we have just created a new topography
        else:
            # Which metadata counts as significant is declared by the schema
            # rather than listed here, so a kind that gains a field does not also
            # have to be added to a set in this module. Fields marked
            # `significant: False` -- the free-text instrument name, and the
            # non-significant entries of the instrument parameters -- are
            # excluded by `significant_values` itself.
            if update_fields is None or "metadata" in update_fields:
                before = old_obj._significant_metadata()
                after = self._significant_metadata()
                refresh_dependent_data = before != after

                if refresh_dependent_data:
                    changed = [
                        name
                        for name in after
                        if before.get(name) != after.get(name)
                    ]
                    _log.debug(
                        f"The following significant metadata of measurement "
                        f"{self.id} changed: "
                    )
                    for name in changed:
                        _log.debug(
                            f"{name}: was '{before.get(name)}', is now "
                            f"'{after.get(name)}'"
                        )

            # `data_source` is the one significant field no schema can declare:
            # it selects *which* channel the metadata describes, rather than
            # describing it. Selecting another channel invalidates everything
            # derived from the data, so it triggers a refresh like a metadata
            # change does.
            if update_fields is None or "data_source" in update_fields:
                if old_obj.data_source != self.data_source:
                    _log.debug(
                        f"The data source (channel) of measurement {self.id} "
                        f"changed: was '{old_obj.data_source}', is now "
                        f"'{self.data_source}'"
                    )
                    refresh_dependent_data = True

        # Check if we need to run the update task
        if refresh_dependent_data:
            run_task(self)
            # run_task sets the pending task state in memory (autosave=False),
            # expecting this save() to persist it. When the caller restricted
            # update_fields (e.g. save(update_fields=["size_x"])) those fields
            # would otherwise be dropped, leaving task_state stale (reported as
            # SUCCESS while a recompute is in flight) and defeating the in-flight
            # re-dispatch guard, which keys off the persisted task_state.
            if update_fields is not None:
                for name in TaskStateModel.PENDING_STATE_FIELDS:
                    if name not in update_fields:
                        update_fields.append(name)

        # Save after run task, because run task may update the task state
        super().save(*args, **kwargs)

    def lazy_delete(self, deleted_by=None):
        """Mark this measurement for deletion.

        `deleted_by` is the user performing the deletion. Pass None for system
        operations.
        """
        self.deleted_at = timezone.now()
        self.deleted_by = deleted_by
        self.save(update_fields=["deleted_at", "deleted_by"])

    def save_datafile(self, fobj):
        self.datafile = Manifest.objects.create(
            permissions=self.permissions,
            filename=self.name,
            kind="raw",
            file=File(fobj),
        )

    def remove_files(self):
        """Remove files associated with a topography instance before removal of the topography."""

        def delete(name, exc=Manifest.DoesNotExist):
            try:
                x = getattr(self, name)
            except exc:
                pass
            else:
                if x:
                    x.delete()

        delete("datafile")
        delete("squeezed_datafile")
        delete("thumbnail")
        delete("deepzoom", ManifestSet.DoesNotExist)

    def __str__(self):
        return "Measurement '{0}'".format(self.name)

    @property
    def label(self):
        """Return a string which can be used in the UI."""
        return self.name

    @property
    def storage_prefix(self):
        """Return prefix used for storage.

        Looks like a relative path to a directory.
        If storage is on filesystem, the prefix should correspond
        to a real directory.
        """
        if self.id is None:
            raise RuntimeError(
                "This `Measurement` does not have an id yet; the storage prefix is not yet known."
            )
        return f"topographies/{self.id}"

    def get_related_surfaces(self):
        """Returns sequence of related surfaces.

        :return: True or False
        """
        return [self.surface]

    def is_shared(self, user) -> bool:
        """Returns True, if this topography is shared with a given user."""
        return self.permissions.get_for_user(user) is not None

    @property
    def instrument_info(self):
        # Build dictionary with instrument information from database... this may override data provided by the
        # topography reader
        instrument = self.meta.instrument
        return {
            "instrument": {
                "name": instrument.name,
                "parameters": instrument.parameters.model_dump(exclude_none=True),
            }
        }

    def _infer_kind_from_datafile(self):
        """
        Derive the kind from the data file without recording it.

        A measurement created from a container carries metadata that came from the
        archive rather than from an inspection, so it has no kind yet but is
        perfectly readable. Deriving it here keeps such a measurement usable; the
        next inspection is what stores the value.

        Raises
        ------
        MeasurementNotInspectedError
            If there is no data file to derive it from.
        """
        # `exists` finalizes a pending upload, so it has to run before the file is
        # read. `read` does this too, but the kind is resolved before `read` is
        # reached, so a measurement whose upload is not yet confirmed would fail
        # here first.
        if not self.datafile_id or not self.datafile.exists():
            raise MeasurementNotInspectedError(
                f"Measurement {self.id} has neither a recorded kind nor a readable "
                "data file to derive one from."
            )
        reader = get_topography_reader(self.datafile.file, format=self.datafile_format)
        channel = reader.channels[
            reader.default_channel.index
            if self.data_source is None
            else self.data_source
        ]
        return infer_kind(channel)

    @property
    def adapter(self):
        """
        The measurement adapter that handles this record.

        Falls back to deriving the kind from the data file for a measurement that
        has not been inspected yet -- importing a container creates exactly such
        records, and they have to stay readable.

        Raises
        ------
        MeasurementNotInspectedError
            If no kind is recorded and there is no data file to derive one from.
        UnknownMeasurementKindError
            If no type is registered for this measurement's kind, i.e. the package
            providing it is not installed.
        """
        return get_adapter(
            self.kind if self.kind is not None else self._infer_kind_from_datafile()
        )

    def _significant_metadata(self):
        """
        The metadata that affects derived data, for change detection in `save`.

        Deliberately does not go through `meta`: with no recorded kind, that
        derives one from the data file, and opening a file during `save` is both
        slow and outside the error handling of the inspection task -- an
        unreadable file would raise here rather than being recorded as a failed
        inspection. Without a kind there is no schema to say which fields matter,
        so the stored document is compared as it is.
        """
        if not self.has_adapter:
            return self.metadata or {}
        return significant_values(self.meta)

    @property
    def meta(self):
        """
        The validated user-facing metadata of this measurement.

        Returns a schema instance rather than the stored dict, so that reading a
        field that does not apply to this kind fails instead of returning None.
        Mutating the returned object does not persist anything; use
        :meth:`update_metadata`.
        """
        return self.adapter.Metadata(**(self.metadata or {}))

    @property
    def info(self):
        """
        The validated file-derived cache of this measurement.

        Written only by the inspection task, so this is read-only as far as the
        rest of the application is concerned.
        """
        return self.adapter.FileInfo(**(self.file_info or {}))

    def update_metadata(self, save=True, **changes):
        """
        Validate and store changes to the user-facing metadata.

        Parameters
        ----------
        save : bool, optional
            Whether to save the measurement. (Default: True)
        **changes
            Metadata fields to change.

        Returns
        -------
        Measurement
            This measurement.

        Raises
        ------
        pydantic.ValidationError
            If a value is invalid, or the field does not exist for this kind.
        """
        metadata = self.meta
        for name, value in changes.items():
            setattr(metadata, name, value)
        self.metadata = dump_metadata(metadata)
        if save:
            self.save(update_fields=["metadata"])
        return self

    def update_file_info(self, save=True, **changes):
        """Validate and store changes to the file-derived cache."""
        info = self.info
        for name, value in changes.items():
            setattr(info, name, value)
        self.file_info = dump_metadata(info)
        if save:
            self.save(update_fields=["file_info"])
        return self

    @property
    def has_adapter(self):
        """
        Whether this measurement's data can be interpreted at all.

        Only considers the recorded kind: this is the cheap check used to decide
        whether a record is interpretable, so it must not open the data file.
        """
        return self.kind is not None and has_adapter(self.kind)

    def _read(self, reader: ReaderBase, apply_filters: bool = True):
        """
        Read the data object from an already opened reader.

        Kept as a thin wrapper because callers outside this class use it; the work
        belongs to the adapter, which knows what the data looks like.
        """
        return self.adapter.read_from_reader(
            self, reader, apply_filters=apply_filters
        )

    def read(
        self,
        allow_squeezed: bool = True,
        apply_filters: bool = True,
        return_reader: bool = False,
    ):
        """Return the in-memory data object for this measurement.

        For the height-data kinds this is a
        SurfaceTopography.Topography/UniformLineScan/NonuniformLineScan instance,
        guaranteed to

        - have a 'unit' property
        - have a size: .physical_sizes
        - have been scaled and detrended with the saved parameters

        It has not necessarily a pipeline with all these steps and a
        'detrend_mode` attribute. This is only always the case if
        allow_squeezed=False. In this case the returned instance was regenerated
        from the original file with additional steps applied.

        If allow_squeezed=True, the returned data may be read from a cached file
        which scaling and detrending already applied.

        Parameters
        ----------
        allow_squeezed: bool, optional
            If True (default), the instance is allowed to be generated
            from a squeezed datafile which is not the original datafile.
            This is often faster than the original file format.
            (Default: True)
        apply_filters: bool, optional
            If True (default), the instance is detrended and corrected for
            missing artifacts according to the saved parameters.
            (Default: True)
        return_reader: bool
            If True, return a tuple containing the data object and the reader.
            (Default: False)

        Raises
        ------
        MeasurementNotInspectedError
            If no kind is recorded and there is no readable data file to derive one
            from. An un-inspected measurement with a data file reads fine.
        UnknownMeasurementKindError
            If the package providing this kind of measurement is not installed.
        """
        return self.adapter.read(
            self,
            allow_canonical=allow_squeezed,
            apply_filters=apply_filters,
            return_reader=return_reader,
        )

    lazy_read = read  # For compatibility with datasets that implement `lazy_read`
    topography = read  # Renaming this, mark `topography` as deprecated before v2

    def to_dict(self):
        """Create dictionary for export of metadata to json or yaml"""
        # FIXME!! This code should be moved to a separate serializer class
        meta = self.meta
        info = self.info
        result = {
            "name": self.name,
            "datafile": {
                "original": self.datafile.filename,
                "squeezed-netcdf": (
                    self.squeezed_datafile.filename if self.squeezed_datafile_id else None
                ),
            },
            "data_source": self.data_source,
            "has_undefined_data": info.has_undefined_data,
            "undefined_data_fraction": info.undefined_data_fraction,
            # A kind that does not support filling or periodicity has no such
            # field; the container format still expects the keys, so they fall
            # back to what the behaviour effectively was.
            "fill_undefined_data_mode": getattr(
                meta, "fill_undefined_data_mode", "do-not-fill"
            ),
            "detrend_mode": meta.detrend_mode,
            "is_periodic": getattr(meta, "is_periodic", False),
            "created_by": {"name": self.created_by.name,
                           "orcid": getattr(self.created_by, 'orcid_id', None)},
            "measurement_date": self.measurement_date,
            "description": self.description,
            "unit": meta.unit,
            "size": (
                [meta.size_x]
                if getattr(meta, "size_y", None) is None
                else [meta.size_x, meta.size_y]
            ),
            "tags": [t.name for t in self.tags.order_by("name")],
            "instrument": {
                "name": meta.instrument.name,
                "type": meta.instrument.type,
                "parameters": meta.instrument.parameters.model_dump(
                    exclude_none=True
                ),
            },
        }
        if info.height_scale_editable:
            result["height_scale"] = meta.height_scale
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
        copy = Measurement.objects.get(pk=self.pk)
        copy.pk = None  # This will lead to the creation of a new instance on save
        copy.task_id = None  # We need to indicate that no tasks have run
        copy.surface = to_surface

        # Set permissions
        copy.permissions = to_surface.permissions

        # Copy datafile
        copy.datafile = self.datafile.deepcopy(to_surface.permissions)

        # Copy attachments
        copy.attachments = self.attachments.deepcopy(to_surface.permissions)

        # Set file names of derived data to None, otherwise they will be deleted and become unavailable to the
        # original topography
        copy.thumbnail = None
        copy.squeezed_datafile = None

        # Copy tags
        copy.tags = self.tags.get_tag_list()

        # Recreate cache to recreate derived files
        _log.info(
            f"Creating cached properties of new {copy.get_subject_type()} {copy.id}..."
        )
        run_task(copy)
        copy.save()  # run_task sets the initial task state to 'pe', so we need to save

        return copy

    def _render_thumbnail(self, width=400, height=400, cmap=None, st_topo=None):
        """
        Make thumbnail image.

        Parameters
        ----------
        width : int, optional
            Maximum width of the thumbnail. (Default: 400)
        height : int, optional
            Maximum height of the thumbnail. (Default: 400)
        cmap : str or colormap, optional
            Color map for rendering the data. (Default: None)
        st_topo : optional
            Already-read data object, to avoid reading it twice. (Default: None)

        Returns
        -------
        image : bytes-like
            Thumbnail image.
        """
        if st_topo is None:
            st_topo = self.read()
        return self.adapter.render_thumbnail(
            self, st_topo, width=width, height=height, cmap=cmap
        )

    def _make_thumbnail(self, st_topo=None):
        """Renews thumbnail.

        Returns
        -------
        None
        """
        if st_topo is None:
            st_topo = self.read()

        image_file = self._render_thumbnail(st_topo=st_topo)

        # Replace the old thumbnail only once the new one has been rendered
        if self.thumbnail is not None:
            self.thumbnail.delete()
        self.thumbnail = write_thumbnail_manifest(self, image_file)

    def _make_deepzoom(self, st_topo=None):
        """Renew deep zoom images.

        Does nothing for kinds that have no Deep Zoom representation.

        Returns
        -------
        None
        """
        if not self.adapter.has_deepzoom:
            return
        if st_topo is None:
            st_topo = self.read()
        if self.deepzoom is not None:
            self.deepzoom.delete()
        self.deepzoom = ManifestSet.objects.create(permissions=self.permissions)
        self.adapter.make_deepzoom(self, st_topo, self.deepzoom)

    def _make_squeezed(self, st_topo=None, save=False):
        """Renew the canonical ("squeezed") data file."""
        if not self.adapter.has_canonical_file:
            return
        if st_topo is None:
            st_topo = self.read(allow_squeezed=False)
        new_datafile = write_canonical_manifest(self, st_topo)
        # Delete the old file only once the new one is written, so a failure part
        # way through leaves the usable file in place.
        if self.squeezed_datafile:
            self.squeezed_datafile.delete()
        self.squeezed_datafile = new_datafile
        if save:
            self.save()

    def make_thumbnail(self, none_on_error=True, st_topo=None):
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
            self._make_thumbnail(st_topo=st_topo)
        except Exception as exc:
            if none_on_error:
                self.thumbnail = None
                self.save(update_fields=["thumbnail"])
                _log.error(
                    "Problems while generating thumbnail for topography %s: %s. "
                    "Saving <None> instead.",
                    self.id,
                    exc,
                    exc_info=True,
                )
            else:
                raise ThumbnailGenerationException(self, str(exc)) from exc

    def make_deepzoom(self, none_on_error=True, st_topo=None):
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
            self._make_deepzoom(st_topo=st_topo)
        except Exception as exc:
            if none_on_error:
                self.deepzoom = None
                self.save(update_fields=["deepzoom"])
                _log.error(
                    "Problems while generating deep zoom images for topography "
                    "%s: %s. Saving <None> instead.",
                    self.id,
                    exc,
                    exc_info=True,
                )
            else:
                raise DZIGenerationException(self, str(exc)) from exc

    def make_squeezed(self, none_on_error=True, st_topo=None, save=False):
        try:
            self._make_squeezed(st_topo=st_topo, save=save)
        except Exception as exc:
            if none_on_error:
                self.squeezed_datafile = None
                self.save(update_fields=["squeezed_datafile"])
                _log.error(
                    "Problems while generating squeezed datafile for topography "
                    "%s: %s. Saving <None> instead.",
                    self.id,
                    exc,
                    exc_info=True,
                )
            else:
                raise SqueezedDatafileGenerationException(self, str(exc)) from exc

    def refresh_bandwidth_cache(self, st_topo=None):
        """Renew bandwidth cache.

        Cache bandwidth for bandwidth plot in database. Data is stored in units of meter.
        """
        if st_topo is None:
            st_topo = self.read()
        if st_topo.unit is not None:
            bandwidth_lower, bandwidth_upper = st_topo.bandwidth()
            fac = get_unit_conversion_factor(st_topo.unit, "m")

            try:
                short_reliability_cutoff = (
                    st_topo.short_reliability_cutoff()
                )  # Return float or None
            except UndefinedDataError:
                # Short reliability cutoff can only be computed on topographies without undefined data
                short_reliability_cutoff = None
            if short_reliability_cutoff is not None:
                short_reliability_cutoff *= fac

            self.update_file_info(
                save=False,
                bandwidth_lower=fac * bandwidth_lower,
                bandwidth_upper=fac * bandwidth_upper,
                # None is also stored here
                short_reliability_cutoff=short_reliability_cutoff,
            )

    @property
    def is_metadata_complete(self):
        """
        Whether we have all the metadata needed to actually read the file.

        Two failures answer the question with False rather than raising, because
        in both of them nothing can say what the measurement still needs:

        - the kind cannot be resolved (none recorded and none derivable, or a kind
          whose plugin is not installed), and
        - the stored document does not validate against the kind's schema, which
          means either corruption or a document written under a different kind.
          That is a fault worth a log line, not a silent False.

        Anything else propagates, and deliberately so. In particular, deriving a
        kind from the data file can fail with `CannotDetectFileFormat`, which
        `TaskStateModel.run_task` translates into a user-facing "unknown or
        unsupported format" error -- reporting it as incomplete metadata instead
        would tell the user to go and enter a size for a file we cannot read.
        """
        try:
            return self.meta.is_complete()
        except MeasurementRegistryError:
            return False
        except pydantic.ValidationError:
            _log.error(
                "Stored metadata of measurement %s does not validate against the "
                "schema of kind '%s'; reporting it as incomplete.",
                self.id,
                self.kind,
                exc_info=True,
            )
            return False

    def notify_users(self, sender, verb, description):
        self.permissions.notify_users(sender, verb, description)

    def refresh_cache(self, timer=None):
        """
        Inspect datafile and renew cached properties, in particular database entries on
        resolution, size etc. and the squeezed NetCDF representation of the data.
        """
        if timer is None:
            timer = Timer("refresh_cache")

        # Send signal
        _log.debug(f"Sending `pre_refresh_cache` signal from {self}...")
        pre_refresh_cache.send(sender=Measurement, instance=self)

        with timer("exists"):
            # First check if we have a datafile
            if not self.datafile.exists():
                raise RuntimeError(
                    f"Measurement {self.id} does not appear to have a data file. Cannot "
                    f"refresh cached data."
                )

        # Check if this is the first time we are opening this file...
        populate_initial_metadata = self.data_source is None

        # Populate datafile information in the database.
        # (We never load the topography in the web server, so we don't know this until
        # the Celery task refreshes the cache. Fields that are undefined are
        # autodetected.)
        _log.info(f"Caching properties of topography {self.id}...")

        # Open topography file
        with timer("get_topography_reader"):
            reader = get_topography_reader(self.datafile.file)
            self.datafile_format = reader.format()

        # Update channel names
        self.channel_names = [
            (channel.name, _get_unit(channel)) for channel in reader.channels
        ]

        # Idiot check
        if len(self.channel_names) == 0:
            raise RuntimeError(
                f"Datafile of measurement '{self.name}' could be opened, but it "
                "appears to contain no valid data."
            )

        # Check whether the user already selected a (valid) channel, if not set to
        # default channel. We compute this into a local variable first so we can
        # reject files with incomplete metadata (below) *before* mutating any
        # significant field (such as `data_source`); otherwise a rejected inspection
        # would leave a phantom change that re-dispatches the task on the terminal
        # save().
        data_source = self.data_source
        if (
            data_source is None
            or data_source < 0
            or data_source >= len(self.channel_names)
        ):
            data_source = reader.default_channel.index

        # Select channel
        channel = reader.channels[data_source]

        # Reject files with incomplete metadata if this instance is configured to do
        # so. The file is of a supported format and could be read, but the metadata
        # required to process it (physical size, unit) is missing and would normally
        # have to be entered manually through the UI. A field is considered missing
        # only if neither the file nor the existing database entry provides it, so
        # container/zip imports (which populate this metadata from `index.json` before
        # inspection) are not affected.
        if getattr(settings, "TOPOBANK_REJECT_INCOMPLETE_METADATA", False):
            stored = self.meta
            size_missing = channel.physical_sizes is None and stored.size_x is None
            unit_missing = channel.unit is None and stored.unit is None
            if size_missing or unit_missing:
                missing = []
                if size_missing:
                    missing.append("physical size")
                if unit_missing:
                    missing.append("unit")
                raise IncompleteMetadataError(
                    f"The file format '{self.datafile_format}' is supported, but the "
                    f"file does not contain complete metadata. The following required "
                    f"metadata could not be read from the file: {', '.join(missing)}. "
                    f"This instance is configured to reject files with incomplete "
                    f"metadata."
                )

        self.data_source = data_source

        # Which kind of measurement this is follows from the selected channel, so it
        # is recorded here rather than guessed from field values later. An existing
        # kind is not overwritten: a measurement keeps the type that created it even
        # if the inference would now pick a different one, so that reprocessing
        # cannot silently reinterpret stored data.
        if self.kind is None:
            self.kind = infer_kind(channel)

        #
        # Look for necessary metadata. We override values in the database. This may be
        # necessary if the underlying reader changes (e.g. through bug fixes).
        #

        # The inspection assembles both documents and applies them at the end, so
        # that a file it ends up rejecting leaves nothing half-written behind.
        metadata = self.meta
        info = self.info

        # Resolution
        if channel.dim == 1:
            (n,) = channel.nb_grid_pts
            info.resolution_x = int(n)
        elif channel.dim == 2:
            info.resolution_x, info.resolution_y = (
                int(n) for n in channel.nb_grid_pts
            )
        else:
            # This should not happen
            raise NotImplementedError(
                f"Cannot handle measurements of dimension {channel.dim}."
            )

        # Size. `*_editable` records whether the file left the value to the user,
        # which is why it belongs to the file-derived document rather than to the
        # metadata the user edits.
        if channel.physical_sizes is None:
            info.size_editable = True
        else:
            info.size_editable = False
            if channel.dim == 1:
                (size_x,) = channel.physical_sizes
                metadata.size_x = float(size_x)
            elif channel.dim == 2:
                size_x, size_y = channel.physical_sizes
                metadata.size_x = float(size_x)
                metadata.size_y = float(size_y)
            else:
                # This should not happen
                raise NotImplementedError(
                    f"Cannot handle measurements of dimension {channel.dim}."
                )

        # Unit
        if channel.unit is None:
            info.unit_editable = True
        else:
            info.unit_editable = False
            if isinstance(channel.unit, tuple):
                raise NotImplementedError(
                    f"Data channel '{channel.name}' contains information that is not "
                    "height."
                )
            metadata.unit = channel.unit

        # Height scale
        if channel.height_scale_factor is None:
            info.height_scale_editable = True
        else:
            info.height_scale_editable = False
            metadata.height_scale = channel.height_scale_factor

        # Periodicity. A nonuniform line scan has no `is_periodic` field at all,
        # so there is nothing to set for it -- what used to be expressed by
        # clearing `is_periodic_editable` is now the shape of its schema.
        if channel.is_uniform:
            info.is_periodic_editable = True
            if not self.metadata:
                metadata.is_periodic = bool(channel.is_periodic)
        else:
            info.is_periodic_editable = False

        #
        # We now look for optional metadata. Only import it from the file on first read,
        # otherwise we may override what the user has painfully adjusted when refreshing
        # the cache.
        #

        if populate_initial_metadata:
            # What can be imported from the file, and how, depends entirely on the
            # reader this kind uses, so the adapter does it.
            self.adapter.read_initial_metadata(self, channel, metadata)

        self.metadata = dump_metadata(metadata)
        self.file_info = dump_metadata(info)

        # Read the file if metadata information is complete
        if self.is_metadata_complete:
            with timer("metadata is complete"):
                _log.info(f"Metadata of {self} is complete. Generating images.")
                with timer("_read"):
                    st_topo = self._read(reader)

                # What reading the data revealed. Which values those are, and how
                # they are obtained, is the adapter's business; recording them is
                # ours.
                self.update_file_info(
                    save=False, **self.adapter.read_file_info(self, st_topo)
                )

                # Refresh other cached quantities
                with timer("refresh_bandwidth_cache"):
                    self.refresh_bandwidth_cache(st_topo=st_topo)
                with timer("make_thumbnail"):
                    self.make_thumbnail(st_topo=st_topo)
                with timer("make_deepzoom"):
                    self.make_deepzoom(st_topo=st_topo)
                with timer("make_squeezed"):
                    self.make_squeezed(st_topo=st_topo)

                # Verify the derived files actually landed. A measurement with
                # complete metadata is expected to have these; a missing one is
                # a silent data-quality failure that would otherwise be masked
                # by task_state=SUCCESS. We only log (generation stays
                # non-fatal) so monitoring can catch it.
                missing = []
                if self.thumbnail is None or not self.thumbnail.exists():
                    missing.append("thumbnail")
                # Only kinds that declare a Deep Zoom representation have one.
                if self.adapter.has_deepzoom and (
                    self.deepzoom is None or len(self.deepzoom) == 0
                ):
                    missing.append("deepzoom")
                if self.adapter.has_canonical_file and (
                    self.squeezed_datafile is None
                    or not self.squeezed_datafile.exists()
                ):
                    missing.append("squeezed_datafile")
                if missing:
                    _log.error(
                        "refresh_cache: topography %s has complete metadata but "
                        "is missing derived files: %s",
                        self.id,
                        ", ".join(missing),
                    )

        # Save dataset
        self.save()

        # Send signal
        _log.debug(f"Sending `post_refresh_cache` signal from {self}...")
        post_refresh_cache.send(sender=Measurement, instance=self)

    def get_undefined_data_status(self):
        """
        Human-readable description of the status of undefined data.

        None for a kind that has no notion of undefined data points; whether the
        notion applies, and what to say about it, is the adapter's to decide.
        """
        return self.adapter.get_undefined_data_status(self)

    def task_worker(self, timer=None):
        self.refresh_cache(timer=timer)

    def ensure_task_started(self):
        """Ensures that the task has started running"""
        if self.task_state == "no" and self.datafile is not None:
            # Need a transaction here to allow run_task to properly use on_commit hooks.
            # Note: This should be reworked in the future since this is called via a GET request.
            with transaction.atomic():
                run_task(self)
                self.save()
