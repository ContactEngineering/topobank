"""
Basic models for the web app for handling topography data.
"""

import itertools
import logging
from collections import defaultdict
from copy import deepcopy
from uuid import uuid4
from typing import List

import django.dispatch
import numpy as np
import tagulous.models as tm
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.core.exceptions import PermissionDenied
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q, Value
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from SurfaceTopography.Container.SurfaceContainer import SurfaceContainer
from SurfaceTopography.IO import ReaderBase
from SurfaceTopography.Metadata import InstrumentParametersModel

from ..authorization import get_permission_model
from ..authorization.mixins import PermissionMixin
from ..authorization.models import (
    AuthorizedManager,
    SurfaceTopographyManager,
    ViewEditFull,
)
from ..files.models import Manifest, ManifestSet
from ..settings import defaults
from ..taskapp.models import TaskStateModel
from ..taskapp.utils import in_celery_worker_process, run_task
from ..utils.timer import Timer
from . import processing
from .processing import (
    DERIVED_NAMES,
    INSPECTED_FIELDS,
    MAX_FILENAME_LENGTH,
    RESULT_VERSION,
    SQUEEZED_DATAFILE_FORMAT,
    InspectionParameters,
    InspectionResult,
    StorageWriter,
    bandwidth_fields,
    delete_keys,
    get_topography_reader,
    inspect_datafile,
    instrument_info,
    missing_derived_files,
    read_topography,
    visualization_topography,
    write_derived,
)

_log = logging.getLogger(__name__)

try:
    from botocore.exceptions import ClientError as _StorageClientError
except ImportError:  # pragma: no cover - botocore ships with boto3
    _StorageClientError = None

# Errors raised when a stored file has been deleted: the manifest row is gone,
# or the bytes are (FileSystemStorage raises FileNotFoundError, S3 a ClientError).
_MISSING_FILE_ERRORS = (Manifest.DoesNotExist, FileNotFoundError) + (
    (_StorageClientError,) if _StorageClientError is not None else ()
)


def _is_missing_file_error(exc) -> bool:
    if _StorageClientError is not None and isinstance(exc, _StorageClientError):
        code = str(exc.response.get("Error", {}).get("Code", ""))
        return code in ("404", "NoSuchKey", "NotFound")
    return True


pre_refresh_cache = django.dispatch.Signal()
post_refresh_cache = django.dispatch.Signal()

MAX_LENGTH_DATAFILE_FORMAT = (
    15  # some more characters than currently needed, we may have sub formats in future
)


def _visualization_detrend_mode():
    return getattr(
        settings,
        "TOPOBANK_VISUALIZATION_DETREND_MODE",
        defaults.TOPOBANK_VISUALIZATION_DETREND_MODE,
    )


def processing_storage_prefix():
    """The folder under which inspections write derived files, one folder per
    measurement and run (see `Topography.processing_folder`)."""
    return getattr(
        settings,
        "TOPOBANK_PROCESSING_STORAGE_PREFIX",
        defaults.TOPOBANK_PROCESSING_STORAGE_PREFIX,
    ).rstrip("/")


def _validate_inspection_result(result, prefix):
    """Refuse a result this code did not write or that points outside `prefix`.

    A result may come back from another process, so it is checked before any of
    it reaches the database: a field outside what an inspection determines, or a
    file outside the inspections' storage prefix, could otherwise overwrite any
    field or make a manifest of (and later delete) any stored object.
    """
    if result.version != RESULT_VERSION:
        raise ValueError(
            f"Cannot apply an inspection result of version {result.version}; this "
            f"is version {RESULT_VERSION}."
        )
    unknown = set(result.fields) - set(INSPECTED_FIELDS)
    if unknown:
        raise ValueError(
            f"An inspection result may not set {', '.join(sorted(unknown))}."
        )
    unknown = set(result.derived) - set(DERIVED_NAMES)
    if unknown:
        raise ValueError(
            f"An inspection result has unknown derived files {', '.join(sorted(unknown))}."
        )
    for name, written in result.derived.items():
        items = written if name == "deepzoom" and isinstance(written, list) else [written]
        for item in items:
            if item is not None and not (
                isinstance(item, dict)
                and isinstance(item.get("key"), str)
                and isinstance(item.get("filename"), str)
                and 0 < len(item["filename"]) <= MAX_FILENAME_LENGTH
                and ".." not in item["filename"].split("/")
                and (
                    item.get("size") is None
                    or (isinstance(item["size"], int) and item["size"] >= 0)
                )
            ):
                raise ValueError(
                    f"An inspection result names a malformed file for {name}."
                )
    keys = result.written_keys()
    if len(set(keys)) < len(keys):
        raise ValueError("An inspection result names a file more than once.")
    for key in keys:
        if not key.startswith(f"{prefix}/") or ".." in key.split("/"):
            raise ValueError(
                f"An inspection result references '{key}', which is not under "
                f"'{prefix}/'."
            )


def _inspected_value(field, value):
    """`value` of `field` as an inspection result holds it, as Python."""
    if isinstance(field, models.DateField) and isinstance(value, str):
        # A date the file gives with a time of day, as it came through JSON
        value = parse_datetime(value) or value
    return field.to_python(value)


def _snapshot(value):
    """`value`, copied if it is a JSON value that can be edited in place."""
    return deepcopy(value) if isinstance(value, (dict, list)) else value


def _delete_all(objs):
    """Delete manifests or folders, logging rather than raising a failure."""
    for obj in objs:
        try:
            obj.delete()
        except Exception as exc:  # deleting is cleanup; never fail on it
            _log.warning("Could not delete derived file %s: %s", obj, exc)


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
        self._topographies = self._surface.topography_set.all()
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

    def num_topographies(self):
        return self.topography_set.count()

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
        self.topography_set.filter(deleted_at__isnull=True).update(
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
        for topography in self.topography_set.select_related("created_by").prefetch_related("tags").all():
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
         surface_dict['topographies'] = [t.to_dict() for t in surface.topography_set.order_by('name')]

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

        for topography in self.topography_set.all():
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


class Topography(PermissionMixin, TaskStateModel, SubjectMixin):
    """
    A single topography measurement of a surface of a specimen.
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

    FILL_UNDEFINED_DATA_MODE_NOFILLING = processing.FILL_UNDEFINED_DATA_MODE_NOFILLING
    FILL_UNDEFINED_DATA_MODE_HARMONIC = "harmonic"

    FILL_UNDEFINED_DATA_MODE_CHOICES = [
        (FILL_UNDEFINED_DATA_MODE_NOFILLING, "Do not fill undefined data points"),
        (
            FILL_UNDEFINED_DATA_MODE_HARMONIC,
            "Interpolate undefined data points with harmonic functions",
        ),
    ]

    # In the order of `processing.DETREND_MODES`
    DETREND_MODE_CHOICES = list(
        zip(
            processing.DETREND_MODES,
            [
                "No detrending, but subtract mean height",
                "Remove tilt",
                "Remove curvature and tilt",
            ],
            strict=True,
        )
    )

    INSTRUMENT_TYPE_UNDEFINED = processing.INSTRUMENT_TYPE_UNDEFINED
    INSTRUMENT_TYPE_MICROSCOPE_BASED = processing.INSTRUMENT_TYPE_MICROSCOPE_BASED
    INSTRUMENT_TYPE_CONTACT_BASED = processing.INSTRUMENT_TYPE_CONTACT_BASED

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
            # Used in: surface.topography_set.all() and filtering by surface__deleted_at
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
    surface = models.ForeignKey(Surface, on_delete=models.CASCADE)

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
    # Fraction (not percentage) of the data points of the measured data that are
    # undefined, in [0, 1]. Null until the measurement has been inspected.
    undefined_data_fraction = models.FloatField(
        null=True, default=None, editable=False
    )
    fill_undefined_data_mode = models.TextField(
        choices=FILL_UNDEFINED_DATA_MODE_CHOICES,
        default=FILL_UNDEFINED_DATA_MODE_NOFILLING,
    )

    detrend_mode = models.TextField(choices=DETREND_MODE_CHOICES, default="center")
    # The trend that was subtracted, as `slope_x`/`slope_y` (dimensionless) and
    # `radius_x`/`radius_y` (in `unit`); see `utils.detrend_parameters`. Null until
    # the measurement has been inspected, empty when the mode fits no trend.
    detrend_parameters = models.JSONField(null=True, default=None, editable=False)

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

    # Derived files that `refresh_cache` replaces
    _DERIVED_FIELDS = ("thumbnail", "deepzoom", "squeezed_datafile")

    # The fields an inspection determines that a user may edit as well. Recording
    # an inspection writes these only where it changed them (see `apply_inspection`)
    _EDITABLE_INSPECTED_FIELDS = frozenset(
        (
            "data_source",
            "size_x",
            "size_y",
            "unit",
            "height_scale",
            "is_periodic",
            "measurement_date",
            "instrument_name",
            "instrument_parameters",
            "instrument_type",
        )
    )

    # Fields owned by the task machinery, which `refresh_cache` never writes
    _TASK_FIELDS = frozenset(TaskStateModel.TASK_FIELDS)

    #
    # Methods
    #
    def task_save_fields(self):
        # `refresh_cache` saves the fields it changed itself
        return TaskStateModel.TASK_RESULT_FIELDS

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
                f"DATAFILE MISSING: Creating datafile manifest for Topography: {self}")
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
            old_obj = Topography._base_manager.get(pk=self.pk)
        except self.DoesNotExist:
            pass  # Do nothing, we have just created a new topography
        else:
            # Check which fields actually changed
            changed_fields = [
                name
                for name in self._significant_fields
                if (update_fields is None or name in update_fields)
                and getattr(self, name) != getattr(old_obj, name)
            ]

            # `instrument_parameters` is special as it can contain non-significant
            # entries
            if update_fields is None or "instrument_parameters" in update_fields:
                if InstrumentParametersModel(
                    **self.instrument_parameters
                ) != InstrumentParametersModel(**old_obj.instrument_parameters):
                    changed_fields += ["instrument_parameters"]

            # We need to refresh if any of the significant fields changed during this save
            refresh_dependent_data = any(changed_fields)

            if refresh_dependent_data:
                _log.debug(
                    f"The following significant fields of topography {self.id} changed: "
                )
                for name in changed_fields:
                    _log.debug(
                        f"{name}: was '{getattr(old_obj, name)}', is now '{getattr(self, name)}'"
                    )

        super().save(*args, **kwargs)

        # Check if we need to run the update task. This comes after the save, so
        # that a run which has not started yet reads the new values: a run still
        # queued needs no second dispatch. A run already under way started from
        # the old values, so it is superseded rather than left to finish with
        # stale results. (`refresh_cache` does not save through this method: what
        # it read from the file is that processing, and dispatches nothing.)
        if refresh_dependent_data:
            if not run_task(self) and self.task_state == TaskStateModel.STARTED:
                run_task(self, force=True)

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
                "This `Topography` does not have an id yet; the storage prefix is not yet known."
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
        return instrument_info(self.instrument_name, self.instrument_parameters)

    @property
    def has_instrument_info(self):
        """Whether the database holds instrument information to read the file with.

        The instrument fields keep their defaults until the first processing
        copies them from the file (`refresh_cache`) or a user enters them. Read
        with those defaults, a file loses its own instrument block (the tip
        radius, say, and with it the reliability cutoff), so an unprocessed
        measurement is read with what the file says instead.
        """
        return (
            self.data_source is not None
            or bool(self.instrument_name)
            or bool(self.instrument_parameters)
            or self.instrument_type != self.INSTRUMENT_TYPE_UNDEFINED
        )

    def _reader_info(self):
        """The `info` to read the file with: the database's, once it has any."""
        return self.instrument_info if self.has_instrument_info else None

    def _read(self, reader: ReaderBase, apply_filters: bool = True):
        """
        Read this measurement from `reader` (see `processing.read_topography`).

        apply_filters: bool, optional
            If True (default), the instance is detrended and corrected for
            missing artifacts according to the saved parameters.
            (Default: True)
        """
        if not in_celery_worker_process() and self.size_y is not None:
            _log.warning(
                "You are requesting to load a (2D) topography and you are not within in a Celery worker "
                "process. This operation is potentially slow and may require a lot of memory - do not use "
                "`Topography.read` within the main Django server!"
            )

        # An unprocessed measurement keeps the file's instrument information
        return read_topography(
            reader,
            self.inspection_parameters(),
            apply_filters=apply_filters,
            with_instrument_info=self.has_instrument_info,
        )

    def read(
        self,
        allow_squeezed: bool = True,
        apply_filters: bool = True,
        return_reader: bool = False,
    ):
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
            If True, return a tuple containing the topography and the reader.
            (Default: False)
        """
        #
        # Try to get topography from cache if possible
        #
        toporeader = None
        topo = None
        if allow_squeezed and self.squeezed_datafile_id and apply_filters:
            if not in_celery_worker_process() and self.size_y is not None:
                _log.warning(
                    "You are requesting to load a (2D) topography and you are not within in a Celery worker "
                    "process. This operation is potentially slow and may require a lot of memory - do not use "
                    "`Topography.read` within the main Django server!"
                )

            # Okay, we can use the squeezed datafile, it's already there.
            topo, toporeader = self._read_squeezed()
            # In the squeezed format, these things are already applied/included:
            # unit, scaling, detrending, physical sizes
            # so don't need to provide them to the .topography() method
            if topo is not None:
                _log.info(
                    f"Using squeezed datafile instead of original datafile for topography id {self.id}."
                )

        # The upload may not have been confirmed yet
        if topo is None:
            if self.datafile.confirm_upload():
                # Read raw file if squeezed file is unavailable
                toporeader = get_topography_reader(
                    self.datafile.file, format=self.datafile_format
                )
                topo = self._read(toporeader, apply_filters=apply_filters)
            else:
                raise RuntimeError(
                    f"Topography {self.id} does not appear to have a data file."
                )

        if return_reader:
            return topo, toporeader
        else:
            return topo

    def _read_squeezed(self):
        """Read the squeezed datafile; `(None, None)` if it has disappeared.

        Reprocessing replaces the squeezed datafile and deletes the old one once
        the new reference is committed. A reader that loaded this measurement
        before that commit can find its file gone: it then follows the current
        reference once, and otherwise falls back to the original datafile.
        """
        # The current reference is read through a local, so that a save of this
        # instance never writes back a reference it merely read through
        manifest = self._derived("squeezed_datafile")
        followed = False
        while manifest is not None:
            try:
                toporeader = get_topography_reader(
                    manifest.file, format=SQUEEZED_DATAFILE_FORMAT
                )
                return (
                    toporeader.topography(info=self._reader_info() or {}),
                    toporeader,
                )
            except _MISSING_FILE_ERRORS as exc:
                if not _is_missing_file_error(exc):
                    raise
                current = (
                    Topography._base_manager.filter(pk=self.pk)
                    .values_list("squeezed_datafile_id", flat=True)
                    .first()
                )
                _log.info(
                    "Squeezed datafile %s of topography %s disappeared while "
                    "reading (%s); current squeezed datafile is %s.",
                    manifest.pk,
                    self.id,
                    exc,
                    current,
                )
                if followed or current is None or current == manifest.pk:
                    return None, None
                manifest = Manifest._base_manager.filter(pk=current).first()
                followed = True
        return None, None

    lazy_read = read  # For compatibility with datasets that implement `lazy_read`
    topography = read  # Renaming this, mark `topography` as deprecated before v2

    def to_dict(self):
        """Create dictionary for export of metadata to json or yaml"""
        # FIXME!! This code should be moved to a separate serializer class
        result = {
            "name": self.name,
            "datafile": {
                "original": self.datafile.filename,
                "squeezed-netcdf": (
                    self.squeezed_datafile.filename if self.squeezed_datafile_id else None
                ),
            },
            "data_source": self.data_source,
            "has_undefined_data": self.has_undefined_data,
            "undefined_data_fraction": self.undefined_data_fraction,
            "fill_undefined_data_mode": self.fill_undefined_data_mode,
            "detrend_mode": self.detrend_mode,
            "is_periodic": self.is_periodic,
            "created_by": {"name": self.created_by.name,
                           "orcid": getattr(self.created_by, 'orcid_id', None)},
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
        copy.pk = None  # This will lead to the creation of a new instance on save
        copy.task_id = None  # We need to indicate that no tasks have run
        # ...and must not inherit an in-flight state, which would block the claim
        copy.task_state = Topography.NOTRUN
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
        copy.deepzoom = None
        copy.squeezed_datafile = None

        # Copy tags
        copy.tags = self.tags.get_tag_list()

        # The copy needs a row before its task can be claimed and dispatched
        copy.save()

        # Recreate cache to recreate derived files
        _log.info(
            f"Creating cached properties of new {copy.get_subject_type()} {copy.id}..."
        )
        run_task(copy)

        return copy

    def _visualization_topography(self, st_topo):
        """
        Return the topography as its thumbnail and deep zoom images show it.

        The images are a visualization, not data. A tilt of the sample across the
        scan easily dwarfs its roughness and then renders as a plain color
        gradient, so a deployment can remove tilt (or curvature) from the images
        through ``TOPOBANK_VISUALIZATION_DETREND_MODE`` even when the
        measurement's own ``detrend_mode`` keeps it. A measurement that is
        already detrended at least that far is shown as it is. Analyses and the
        squeezed datafile are unaffected.

        Parameters
        ----------
        st_topo : SurfaceTopography.Topography or line scan
            The measurement as read with its own filters applied.

        Returns
        -------
        st_topo : SurfaceTopography.Topography or line scan
            The topography to render.
        """
        return visualization_topography(
            st_topo, self.detrend_mode, _visualization_detrend_mode()
        )

    def _make_thumbnail(self, st_topo=None):
        """Renews thumbnail.

        Returns
        -------
        None
        """
        if st_topo is None:
            st_topo = self.read()
        self._make_derived("thumbnail", st_topo)

    def _make_deepzoom(self, st_topo=None):
        """Renew deep zoom images.

        Returns
        -------
        None
        """
        if st_topo is None:
            st_topo = self.read()
        if self.size_y is not None:
            # This is a topography (map), we need to create a Deep Zoom Image
            self._make_derived("deepzoom", st_topo)

    def _make_squeezed(self, st_topo=None):
        if st_topo is None:
            st_topo = self.read(allow_squeezed=False)
        self._make_derived("squeezed_datafile", st_topo)

    def _make_derived(self, name, st_topo):
        """Write the derived file `name` alone, as an inspection does, and point
        the field at it. The field is saved (a measurement without a row yet
        excepted), and the file it replaces deleted after that."""
        writer = StorageWriter(default_storage, self.processing_folder(uuid4().hex))
        written = write_derived(
            name,
            st_topo,
            self.inspection_parameters(filename=self.datafile.filename),
            writer,
        )
        attname = f"{name}_id"
        previous = getattr(self, attname)
        try:
            with transaction.atomic():
                retired = self._attach_derived(
                    InspectionResult(derived={name: written}), row=None
                )
                if self.pk is not None:
                    models.Model.save(self, update_fields=[name])
        except BaseException:
            # The manifests it was attached as are gone with the rollback
            setattr(self, attname, previous)
            writer.delete()
            raise
        _delete_all(retired)

    def _derived(self, name):
        """The derived manifest or folder in field `name`, or None.

        None as well when it has been deleted since this instance was loaded, as
        a concurrent refresh does once it has replaced it.
        """
        try:
            return getattr(self, name)
        except self._meta.get_field(name).related_model.DoesNotExist:
            return None

    def _clear_derived(self, name):
        """Drop the derived file in field `name` after generating it failed.

        The field is saved first, and the file deleted after; a failure to delete
        it is only logged (see `_delete_all`). A file that is replaced is retired
        by `_attach_derived` instead.
        """
        old = self._derived(name)
        setattr(self, name, None)
        if self.pk is not None:
            self.save(update_fields=[name])
        if old is not None:
            _delete_all([old])

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
        except SoftTimeLimitExceeded:
            # The worker is out of time, which is no fault of the thumbnail
            raise
        except Exception as exc:
            if none_on_error:
                self._clear_derived("thumbnail")
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
        except SoftTimeLimitExceeded:
            raise
        except Exception as exc:
            if none_on_error:
                self._clear_derived("deepzoom")
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
        """Renew the squeezed datafile.

        `save` is accepted for compatibility only: the field is always saved
        (see `_make_derived`).
        """
        try:
            self._make_squeezed(st_topo=st_topo)
        except SoftTimeLimitExceeded:
            raise
        except Exception as exc:
            if none_on_error:
                self._clear_derived("squeezed_datafile")
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
        for name, value in bandwidth_fields(st_topo).items():
            setattr(self, name, value)

    @property
    def is_metadata_complete(self):
        """Check whether we have all metadata to actually read the file"""
        return (
            self.size_x is not None
            and self.unit is not None
            and self.height_scale is not None
        )

    def notify_users(self, sender, verb, description):
        self.permissions.notify_users(sender, verb, description)

    def inspection_parameters(self, filename=""):
        """What `processing.inspect_datafile` needs to know about this measurement.

        `filename` is the data file's name, which the squeezed datafile is named
        after; reading the measurement does not need it.
        """
        return InspectionParameters(
            name=self.name,
            filename=filename,
            data_source=self.data_source,
            size_x=self.size_x,
            size_y=self.size_y,
            unit=self.unit,
            height_scale=self.height_scale,
            is_periodic=self.is_periodic,
            fill_undefined_data_mode=self.fill_undefined_data_mode,
            detrend_mode=self.detrend_mode,
            instrument_name=self.instrument_name,
            instrument_parameters=self.instrument_parameters,
            thumbnail_format=getattr(
                settings,
                "TOPOBANK_THUMBNAIL_FORMAT",
                defaults.TOPOBANK_THUMBNAIL_FORMAT,
            ),
            visualization_detrend_mode=_visualization_detrend_mode(),
            reject_incomplete_metadata=getattr(
                settings, "TOPOBANK_REJECT_INCOMPLETE_METADATA", False
            ),
        )

    def refresh_cache(self, timer=None):
        """
        Inspect datafile and renew cached properties, in particular database entries on
        resolution, size etc. and the squeezed NetCDF representation of the data.

        The two halves of processing, run here in turn: `processing.inspect_datafile`
        reads the file and writes the derived files under a fresh storage prefix,
        and `apply_inspection` records what it found.
        """
        if timer is None:
            timer = Timer("refresh_cache")

        # Send signal
        _log.debug(f"Sending `pre_refresh_cache` signal from {self}...")
        pre_refresh_cache.send(sender=Topography, instance=self)

        with timer("confirm_upload"):
            # First check if we have a datafile, confirming its upload if it has
            # arrived
            if not self.datafile.confirm_upload():
                raise RuntimeError(
                    f"Topography {self.id} does not appear to have a data file. Cannot "
                    f"refresh cached data."
                )

        # Within a run, under the run's folder, so that what the run leaves
        # behind is found by its task id; in a folder of its own for each
        # attempt, as a redelivered message runs again under the same task id
        if self._task_run is None:
            folder = self.processing_folder(uuid4().hex)
        else:
            folder = f"{self.processing_folder(self._task_run[0])}/{uuid4().hex}"
        writer = StorageWriter(default_storage, folder)
        result = None
        try:
            result = inspect_datafile(
                self.datafile.file,
                self.inspection_parameters(filename=self.datafile.filename),
                writer,
                timer=timer,
                label=self.id,
            )
            saved = self.apply_inspection(result, prefix=writer.prefix)
        except Exception as exc:
            # Whether the inspection or recording it failed, the files it wrote
            # are referenced by nothing and must go. What it found is still
            # recorded, without them.
            writer.delete()
            found = getattr(exc, "inspection_result", None) or result
            if found is not None:
                self._apply_failed_inspection(
                    InspectionResult(fields=found.fields), writer.prefix
                )
            raise

        if saved:
            # Send signal
            _log.debug(f"Sending `post_refresh_cache` signal from {self}...")
            post_refresh_cache.send(sender=Topography, instance=self)

    def _apply_failed_inspection(self, result, prefix):
        """Record what a failed inspection found, without masking its error.

        The error is the task's result, so nothing here may replace it: a failure
        of this itself (e.g. a database transaction the error has already broken)
        is only logged.
        """
        if result is None:
            return
        try:
            self.apply_inspection(result, prefix=prefix, failed=True)
        except Exception:
            _log.exception(
                "refresh_cache: recording the failed inspection of topography %s "
                "failed as well",
                self.id,
            )

    def apply_inspection(self, result, *, prefix, failed=False):
        """Record an inspection's `result` and swap in the derived files it wrote.

        Writes the fields the result determines, of those a user may edit as well
        only the ones it changed, so that edits made while the file was being
        processed survive; recording them never dispatches the processing again.
        Nothing is written once the run in progress on this instance (see
        `TaskStateModel.run_task`) has been superseded by a newer dispatch, and
        the files the result references are deleted instead. Otherwise the
        derived files it replaces are deleted once the transaction commits.

        A `failed` inspection keeps the previous derived files. Within a run it
        still records the other fields it found, as the full-row save at the end
        of a run used to; outside a run it writes nothing.

        The result is checked before anything is written: its version, the fields
        it may set, and that its files lie under `prefix`, the folder of the run
        that wrote them (see `processing_folder`); files are only ever
        deleted from there. Returns whether the result was recorded.
        """
        _validate_inspection_result(result, prefix)
        in_task_run = self._task_run is not None

        if failed:
            self._discard(result.written_keys(), prefix)
            if not in_task_run:
                return False
            result = InspectionResult(fields=result.fields)
        changed = []
        for name, value in result.fields.items():
            field = self._meta.get_field(name)
            loaded = _snapshot(getattr(self, field.attname))
            setattr(self, field.attname, _inspected_value(field, value))
            if (
                name not in self._EDITABLE_INSPECTED_FIELDS
                or getattr(self, field.attname) != loaded
            ):
                changed.append(name)

        previous = {
            f"{name}_id": getattr(self, f"{name}_id") for name in self._DERIVED_FIELDS
        }
        try:
            return self._record_inspection(result, prefix, changed)
        except BaseException:
            # Back to the derived files the database still has: the ones this
            # result was attached as are gone with the rollback
            for attname, pk in previous.items():
                setattr(self, attname, pk)
            raise

    def _record_inspection(self, result, prefix, changed):
        if self.pk is None:
            # A measurement inspected before it was ever saved: nothing can have
            # changed concurrently and nothing references the old files.
            with transaction.atomic():
                retired = self._attach_derived(result, row=None)
                self._save_inspection()
            _delete_all(retired)
            return True

        # A save sets the `auto_now` fields, as it always has
        fields = (
            changed
            + list(result.derived)
            + [f.name for f in self._meta.concrete_fields if getattr(f, "auto_now", False)]
        )
        with transaction.atomic():
            row = self._lock_row(*(f"{name}_id" for name in self._DERIVED_FIELDS))
            if row is None:
                _log.warning(
                    "refresh_cache: topography %s was deleted while it was being "
                    "processed; discarding the results.",
                    self.id,
                )
                self._discard(result.written_keys(), prefix)
                return False
            if not self.is_current_task_run(row):
                _log.warning(
                    "refresh_cache: topography %s was dispatched again while run "
                    "%s was processing it; discarding the results of this run.",
                    self.id,
                    self.task_id,
                )
                self._discard(result.written_keys(), prefix, row)
                return False
            retired = self._attach_derived(result, row)
            missing = missing_derived_files(result, is_map=self.size_y is not None)
            if missing:
                # A measurement with complete metadata is expected to have these;
                # a missing one is a silent data-quality failure that would
                # otherwise be masked by task_state=SUCCESS. We only log
                # (generation stays non-fatal) so monitoring can catch it.
                _log.error(
                    "refresh_cache: topography %s has complete metadata but "
                    "is missing derived files: %s",
                    self.id,
                    ", ".join(missing),
                )
            self._save_inspection(update_fields=fields)
            transaction.on_commit(lambda: _delete_all(retired))
        return True

    def _discard(self, keys, prefix, row=None):
        """Delete the files `keys` in the run folder `prefix` that this
        measurement does not reference; keys elsewhere are left alone.

        A result that was applied before, and is now delivered again, references
        files that are still in use. Only this measurement's own derived files can
        reference them: they lie in the folder of the run that wrote them, and a
        copy of a measurement gets derived files of its own. `row` holds the
        derived-file fields as the caller has locked them; without it they are
        read. The files are deleted once the transaction commits.
        """
        keys = {
            key
            for key in keys
            if isinstance(key, str)
            and key.startswith(f"{prefix}/")
            and ".." not in key.split("/")
        }
        if not keys:
            return
        if row is None and self.pk is not None:
            row = (
                type(self)
                ._base_manager.filter(pk=self.pk)
                .values(*(f"{name}_id" for name in self._DERIVED_FIELDS))
                .first()
            )
        if row is not None:
            ids = [row["thumbnail_id"], row["squeezed_datafile_id"]]
            own = Q(pk__in=[pk for pk in ids if pk is not None])
            if row["deepzoom_id"] is not None:
                own |= Q(folder_id=row["deepzoom_id"])
            keys -= set(
                Manifest.objects.filter(own, file__in=keys).values_list(
                    "file", flat=True
                )
            )
        transaction.on_commit(lambda: delete_keys(default_storage, sorted(keys)))

    def processing_folder(self, run):
        """The storage folder in which run `run` of this measurement writes its
        derived files. Nothing outside it is ever deleted on the run's behalf."""
        owner = "new" if self.pk is None else self.pk
        return f"{processing_storage_prefix()}/{owner}/{run}"

    def _save_inspection(self, update_fields=None):
        """Save what an inspection found, without dispatching another.

        Writes `update_fields` through `models.Model.save`, bypassing `save`,
        which would dispatch the very processing this is. A measurement without a
        row yet is inserted in full, which dispatches nothing either.
        """
        if self.pk is None:
            self.save()
        else:
            models.Model.save(self, update_fields=update_fields)

    def _attach_derived(self, result, row):
        """Point the derived-file fields at the files `result` wrote.

        Creates the manifests (and the deep zoom folder) for files already in
        storage, without copying them. Returns the manifests and folders they
        replace: the ones `row` references (the row as locked now, so that files
        a concurrent refresh swapped in are replaced too), or this instance does
        when there is no row yet.
        """
        now = timezone.now()
        retired = []
        for name, written in result.derived.items():
            attname = f"{name}_id"
            old_id = getattr(self, attname) if row is None else row[attname]
            files = (written if isinstance(written, list) else [written]) if written else []
            if old_id is not None and files and self._references(name, old_id, files):
                # This result was applied before (a redelivery): keep its files,
                # whose objects a replacement would delete
                setattr(self, attname, old_id)
                continue
            new = None
            if files:
                folder = None
                if name == "deepzoom":
                    folder = new = ManifestSet.objects.create(
                        permissions=self.permissions
                    )
                manifests = Manifest.objects.bulk_create(
                    [
                        Manifest(
                            permissions=self.permissions,
                            folder=folder,
                            filename=item["filename"],
                            kind="der",
                            file=item["key"],
                            confirmed_at=now,
                            size_bytes=item.get("size"),
                        )
                        for item in files
                    ]
                )
                if folder is None:
                    (new,) = manifests
            setattr(self, name, new)
            if old_id is not None and old_id != (new.pk if new else None):
                model = self._meta.get_field(name).related_model
                old = model._base_manager.filter(pk=old_id).first()
                if old is not None:
                    retired.append(old)
        return retired

    def _references(self, name, pk, files):
        """Whether the derived manifest or folder `pk` holds the written `files`."""
        keys = {item["key"] for item in files}
        if name == "deepzoom":
            return Manifest.objects.filter(folder_id=pk, file__in=keys).exists()
        return Manifest.objects.filter(pk=pk, file__in=keys).exists()

    def get_undefined_data_status(self):
        """Get human-readable description about status of undefined data as string."""
        s = self.HAS_UNDEFINED_DATA_DESCRIPTION[self.has_undefined_data]
        if self.has_undefined_data and self.undefined_data_fraction is not None:
            percentage = f"{100 * self.undefined_data_fraction:.2g}"
            s += f" {percentage}% of the data points are undefined."
        if (
            self.fill_undefined_data_mode
            == Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING
        ):
            s += " No correction of undefined data is performed."
        elif (
            self.fill_undefined_data_mode
            == Topography.FILL_UNDEFINED_DATA_MODE_HARMONIC
        ):
            s += (
                " Undefined/missing values are filled in with values obtained from a "
                "harmonic interpolation."
            )
        return s

    def task_worker(self, timer=None):
        self.refresh_cache(timer=timer)

    def ensure_task_started(self):
        """Ensures that the task has started running"""
        if self.task_state == "no" and self.datafile is not None:
            # Note: This should be reworked in the future since this is called via a GET request.
            # The instance may be stale: process the measurement only if it still
            # has not been processed, rather than reprocessing one that has since.
            run_task(self, from_states=(TaskStateModel.NOTRUN,))
