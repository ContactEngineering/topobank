"""
Basic models for the web app for handling measurement data.
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
from django.db import models, transaction
from django.db.models import Q, Value
from django.db.models.fields.json import KeyTextTransform
from django.utils import timezone
from SurfaceTopography.Container.SurfaceContainer import SurfaceContainer

from ..authorization import get_permission_model
from ..authorization.mixins import PermissionMixin
from ..authorization.models import (
    AuthorizedManager,
    SurfaceTopographyManager,
    ViewEditFull,
)
from ..files.models import Manifest, ManifestSet
from ..measurements.channels import (
    ChannelError,
    UnsupportedChannelError,
    resolve_channel,
)
from ..measurements.registry import (
    MeasurementNotInspectedError,
    MeasurementRegistryError,
    get_measurement_type,
    get_measurement_types,
    sniff_measurement_file,
)
from ..measurements.schemas import (
    coerce_metadata,
    dump_metadata,
    significant_values,
)
from ..taskapp.models import IncompleteMetadataError, TaskStateModel
from ..taskapp.utils import in_celery_worker_process, run_task
from ..utils.timer import Timer

_log = logging.getLogger(__name__)

pre_refresh_cache = django.dispatch.Signal()
post_refresh_cache = django.dispatch.Signal()

MAX_LENGTH_DATAFILE_FORMAT = (
    15  # some more characters than currently needed, we may have sub formats in future
)


class ThumbnailGenerationException(Exception):
    """Failure while generating thumbnails for a measurement."""

    def __init__(self, measurement, message):
        self._measurement = measurement
        self._message = message

    def __str__(self):
        return self._message


class DZIGenerationException(ThumbnailGenerationException):
    """Failure while generating DZI files for a measurement."""

    pass


class SqueezedDatafileGenerationException(ThumbnailGenerationException):
    """Failure while generating squeezed data files for a measurement."""

    pass


class TopobankLazySurfaceContainer(SurfaceContainer):
    """
    Wraps a `Surface` with lazy loading of measurement data.

    Only measurements whose data is a `SurfaceTopography` object can be part of a
    container, so measurements of other kinds (a spectrum, say) are skipped.

    Measurements that have not been inspected yet are skipped too - their kind is
    not known, so there is no way to tell whether they belong here. That is a
    transient state, but it makes the container quietly smaller than the dataset,
    which would otherwise be indistinguishable from a dataset that really has
    fewer measurements. It is therefore logged.
    """

    def __init__(self, surface, **kwargs):
        self._surface = surface
        topography_kinds = [
            kind
            for kind, measurement_type in get_measurement_types().items()
            if measurement_type.yields_surface_topography
        ]
        self._measurements = self._surface.measurements.filter(
            kind__in=topography_kinds
        )
        self._kwargs = kwargs

        not_inspected = list(
            self._surface.measurements.filter(kind="").values_list("id", flat=True)
        )
        if not_inspected:
            _log.warning(
                "Dataset %s contains %s measurement(s) that have not been "
                "inspected yet (ids: %s); they are not part of this container. "
                "Anything computed from it covers only the remaining %s "
                "measurement(s).",
                surface.id,
                len(not_inspected),
                ", ".join(str(pk) for pk in not_inspected),
                self._measurements.count(),
            )

    def __len__(self):
        return len(self._measurements)

    def __getitem__(self, item):
        return self._measurements[item].read(**self._kwargs)


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

    There can be many measurements for one surface.
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
            # Used in: list queries with deletion_time filter
            models.Index(fields=['deletion_time', 'name'], name='surface_list_idx'),
            # Partial index for active (non-deleted) surfaces
            # Most common query: only show surfaces where deletion_time IS NULL
            # More efficient than full index since it excludes soft-deleted rows
            models.Index(
                fields=['name'],
                name='surface_active_name_idx',
                condition=Q(deletion_time__isnull=True)
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
    deletion_time = models.DateTimeField(null=True)

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

    def lazy_delete(self):
        self.deletion_time = timezone.now()
        self.save(update_fields=["deletion_time"])
        self.measurements.filter(deletion_time__isnull=True).update(
            deletion_time=self.deletion_time
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
        for measurement in self.measurements.all():
            parts += [
                flatten_for_search(measurement.name),
                measurement.description or "",
                (
                    measurement.created_by.name
                    if measurement.created_by is not None
                    else ""
                ),
            ]
            parts += [
                flatten_for_search(tag.name) for tag in measurement.tags.all()
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
         surface_dict['measurements'] = [
             m.to_dict() for m in surface.measurements.order_by('name')
         ]

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

        for measurement in self.measurements.all():
            measurement.deepcopy(surface)
            # we pass the surface here because there is a constraint that (surface_id +
            # measurement name) must be unique, i.e. a surface should never have two
            # measurements of the same name, so we can't set the new surface as the
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
    A single measurement on a specimen.

    This model is deliberately generic. It owns identity, relations, permissions,
    files and task state; everything that depends on *what kind* of measurement it
    is - which metadata it has, how its data file is read, which derived artifacts
    exist - lives in the measurement type registered for :attr:`kind`. See
    :mod:`topobank.measurements`.

    Metadata is stored in two JSON documents rather than in typed columns, and
    validated through pydantic schemas that the measurement type provides:

    :attr:`metadata`
        User-facing physical metadata (sizes, units, corrections, instrument).
        Edited through the API, validated on every write.
    :attr:`file_info`
        Read-only cache of what was found in the data file (resolution,
        bandwidths, the channel inventory). Written only by the inspection task.
    """

    celery_queue = settings.TOPOBANK_MANAGER_QUEUE

    class Meta:
        ordering = ["measurement_date", "pk"]
        unique_together = (("surface", "name"),)
        indexes = [
            # Index on surface foreign key for JOIN optimization
            # Used in: surface.measurements.all() and filtering by
            # surface__deletion_time
            models.Index(fields=["surface"], name="measurement_surface_idx"),
            # Composite index for filtering and ordering
            # Used in: list queries with deletion_time filter
            models.Index(
                fields=["deletion_time", "name"], name="measurement_list_idx"
            ),
            # Partial index for active (non-deleted) measurements
            # Most common query: only show measurements where deletion_time IS NULL
            # More efficient than full index since it excludes soft-deleted rows
            models.Index(
                fields=["name"],
                name="measurement_active_name_idx",
                condition=Q(deletion_time__isnull=True),
            ),
            # Measurements are routinely filtered by kind, e.g. to restrict a
            # container to the kinds that yield SurfaceTopography objects.
            models.Index(fields=["kind"], name="measurement_kind_idx"),
        ]
        constraints = [
            # The `kind` column is the source of truth for queries, while the
            # copy inside `metadata` makes the stored JSON self-describing. This
            # guards against the two drifting apart. Rows that have not been
            # inspected yet have an empty kind and no metadata, in which case the
            # comparison is NULL and the constraint passes.
            models.CheckConstraint(
                condition=Q(kind=KeyTextTransform("kind", "metadata")),
                name="measurement_kind_matches_metadata",
            ),
        ]

    #
    # Manager
    #
    # Automatically filter out deleted measurements in the default manager.
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
    # User who created this measurement
    #
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    #
    # User who last updated this measurement (no reverse lookup needed)
    #
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    #
    # Organization owning this measurement. (Cleanup only happens if the surface is deleted)
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
    deletion_time = models.DateTimeField(null=True)

    #
    # Fields related to raw data
    #
    datafile = models.ForeignKey(
        Manifest,
        null=True,
        on_delete=models.SET_NULL,
        related_name="measurement_datafiles",
    )
    datafile_format = models.CharField(
        max_length=MAX_LENGTH_DATAFILE_FORMAT, null=True, default=None, blank=True
    )
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
        related_name="measurement_squeezed_datafiles",
    )

    #
    # Kind of measurement and its metadata
    #
    # `kind` is the key of the registered measurement type; it is deliberately a
    # plain string rather than a set of choices, because the valid values are
    # whatever is in the registry at runtime and plugins may extend that set.
    # Empty until the data file has been inspected.
    #
    kind = models.CharField(max_length=64, blank=True, default="", db_index=True)
    # Validated against the measurement type's `Metadata` schema.
    metadata = models.JSONField(default=dict)
    # Validated against the measurement type's `FileInfo` schema. Written only by
    # the inspection task, never by the user.
    file_info = models.JSONField(default=dict, editable=False)

    #
    # Selection of the data channel within the data file
    #
    # Channels are identified by name, so that a reader which reports its channels
    # in a different order cannot silently change which data a measurement refers
    # to. None until the data file has been inspected.
    #
    channel_name = models.TextField(null=True, default=None, blank=True)
    # Tie-breaker for data files that contain several channels of the same name.
    # Set *only* when the name is ambiguous; a NULL therefore asserts that the
    # name matched exactly one channel when it was selected, and a name that
    # later becomes ambiguous is reported rather than silently resolved.
    channel_occurrence = models.PositiveIntegerField(null=True, default=None)
    # Transitional: containers written before channels were identified by name
    # record a channel *index*. Import stores it here, and the first inspection
    # consumes it to look up the channel name, then clears it. Nothing else
    # should ever set this.
    channel_index_hint = models.PositiveIntegerField(
        null=True, default=None, editable=False
    )

    #
    # Thumbnail and deep zoom files
    #
    thumbnail = models.ForeignKey(
        Manifest,
        null=True,
        on_delete=models.SET_NULL,
        related_name="measurement_thumbnails",
    )
    deepzoom = models.ForeignKey(
        ManifestSet,
        null=True,
        on_delete=models.SET_NULL,
        related_name="measurement_deepzooms",
    )

    #
    # Changes in these fields trigger a refresh of the cache and of all analyses.
    # `metadata` is handled separately, because only some of its entries are
    # significant (see `topobank.measurements.schemas.significant_values`).
    #
    _significant_fields = {
        "kind",
        "channel_name",
        "channel_occurrence",
    }

    #
    # Measurement type and metadata access
    #

    def get_type(self):
        """
        Return the measurement type for this measurement's kind.

        Raises
        ------
        MeasurementNotInspectedError
            If the data file has not been inspected yet, so the kind is unknown.
        UnknownMeasurementKindError
            If no measurement type is registered for this kind, e.g. because the
            plugin providing it is not installed. The record itself stays usable:
            it can be listed, downloaded and deleted.
        """
        if not self.kind:
            raise MeasurementNotInspectedError(
                f"The kind of measurement {self.id} is not known yet because its "
                "data file has not been inspected."
            )
        return get_measurement_type(self.kind)

    @property
    def meta(self):
        """
        Stored metadata, parsed into the measurement type's pydantic schema.

        This is the typed view of :attr:`metadata`. It is parsed on each access,
        so mutating the returned object does not change what is stored; use
        :meth:`update_metadata` for that.
        """
        return self.get_type().Metadata(**(self.metadata or {}))

    @property
    def info(self):
        """
        File-derived cache, parsed into the measurement type's pydantic schema.

        The typed view of :attr:`file_info`, populated by the inspection task.
        """
        return self.get_type().FileInfo(**(self.file_info or {}))

    def metadata_for_kind(self, kind):
        """
        Return the stored metadata as an instance of `kind`'s schema.

        Values that the target schema does not have, or does not accept, fall
        back to its defaults. This is what lets a user's adjustments survive a
        change of kind, which happens when a different channel of the data file
        is selected.
        """
        return coerce_metadata(get_measurement_type(kind).Metadata, self.metadata)

    def update_metadata(self, save=True, **changes):
        """
        Validate and store changes to the metadata.

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
            If a value is invalid, or a field does not exist for this kind.
        """
        metadata = self.meta
        for name, value in changes.items():
            setattr(metadata, name, value)
        self.metadata = dump_metadata(metadata)
        if save:
            self.save(update_fields=["metadata"])
        return self

    @property
    def is_metadata_complete(self):
        """Whether we have all metadata needed to actually read the data file."""
        try:
            return self.meta.is_complete()
        except MeasurementRegistryError:
            return False

    @property
    def is_first_inspection(self):
        """
        Whether no metadata has been established for this measurement yet.

        Optional metadata (acquisition date, instrument) is imported from the data
        file only on the first inspection; on later ones that would overwrite
        values the user has adjusted. Measurements created from a container
        already carry metadata, so their files are not consulted for it either.
        """
        return not self.metadata

    def get_undefined_data_status(self):
        """Human-readable description of the status of undefined data."""
        return self.info.get_undefined_data_status(
            getattr(self.meta, "fill_undefined_data_mode", None)
        )

    #
    # Channel selection
    #

    def resolve_channel_index(self, reader=None, channel_names=None):
        """
        Return the index of the selected channel.

        Parameters
        ----------
        reader : ReaderBase, optional
            Open reader whose channels are searched.
        channel_names : sequence of str, optional
            Channel names to search, instead of taking them from `reader`.

        Returns
        -------
        int
            Index of the channel in file order.

        Raises
        ------
        ChannelNotFoundError, AmbiguousChannelError
            If the recorded name does not identify exactly one channel; see
            :mod:`topobank.measurements.channels`.
        """
        if channel_names is None:
            channel_names = [channel.name for channel in reader.channels]
        if self.channel_name is None:
            raise ChannelError(
                f"Measurement {self.id} has no channel selected because its data "
                "file has not been inspected yet."
            )
        return resolve_channel(
            channel_names, self.channel_name, self.channel_occurrence
        )

    def warn_if_expensive_read(self):
        """Warn when costly data is loaded outside a Celery worker process."""
        try:
            expensive = self.get_type().is_expensive_to_read
        except MeasurementRegistryError:
            expensive = False
        if expensive and not in_celery_worker_process():
            _log.warning(
                "You are requesting to load a (2D) measurement and you are not within in a Celery worker "
                "process. This operation is potentially slow and may require a lot of memory - do not use "
                "`Measurement.read` within the main Django server!"
            )

    #
    # Persistence
    #

    def save(self, *args, **kwargs):
        update_fields: list = kwargs.get("update_fields", None)
        created = self.pk is None
        if created:
            if self.permissions is None:
                _log.debug(
                    f"NEW MEASUREMENT: Attaching measurement to surface permissions {self}."
                )
                if self.surface.permissions is not None:
                    self.permissions = self.surface.permissions
                else:
                    raise RuntimeError(
                        "Cannot create measurement because surface has no permissions."
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
                f"DATAFILE MISSING: Creating datafile manifest for measurement: {self}")
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
            pass  # Do nothing, we have just created a new measurement
        else:
            changed_fields = [
                name
                for name in self._significant_fields
                if (update_fields is None or name in update_fields)
                and getattr(self, name) != getattr(old_obj, name)
            ]

            # `metadata` is special: only some of its entries affect derived
            # data, so the significant ones are compared rather than the raw
            # document.
            if update_fields is None or "metadata" in update_fields:
                if self._significant_metadata() != old_obj._significant_metadata():
                    changed_fields += ["metadata"]

            # We need to refresh if any of the significant fields changed during this save
            refresh_dependent_data = bool(changed_fields)

            if refresh_dependent_data:
                _log.debug(
                    f"The following significant fields of measurement {self.id} changed: "
                )
                for name in changed_fields:
                    _log.debug(
                        f"{name}: was '{getattr(old_obj, name)}', is now '{getattr(self, name)}'"
                    )

        # Check if we need to run the update task
        if refresh_dependent_data:
            run_task(self)
            # run_task sets the pending task state in memory (autosave=False),
            # expecting this save() to persist it. When the caller restricted
            # update_fields (e.g. save(update_fields=["metadata"])) those fields
            # would otherwise be dropped, leaving task_state stale (reported as
            # SUCCESS while a recompute is in flight) and defeating the in-flight
            # re-dispatch guard, which keys off the persisted task_state.
            if update_fields is not None:
                for name in TaskStateModel.PENDING_STATE_FIELDS:
                    if name not in update_fields:
                        update_fields.append(name)

        # Save after run task, because run task may update the task state
        super().save(*args, **kwargs)

    def _significant_metadata(self):
        """
        Return the metadata entries that affect derived data.

        Falls back to the raw document if the metadata cannot be parsed, which is
        the case for a measurement whose kind is not (or no longer) registered.
        Such a measurement can still be saved; only its metadata cannot be
        interpreted.
        """
        try:
            return significant_values(self.meta)
        except (MeasurementRegistryError, pydantic.ValidationError):
            return dict(self.metadata or {})

    def lazy_delete(self):
        self.deletion_time = timezone.now()
        self.save(update_fields=["deletion_time"])

    def save_datafile(self, fobj):
        self.datafile = Manifest.objects.create(
            permissions=self.permissions,
            filename=self.name,
            kind="raw",
            file=File(fobj),
        )

    def remove_files(self):
        """Remove files associated with a measurement instance before removal of the measurement."""

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

        Note: this deliberately still says "topographies". The files of existing
        measurements live under that prefix in object storage, and renaming it
        would mean moving every stored object.
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
        """Returns True, if this measurement is shared with a given user."""
        return self.permissions.get_for_user(user) is not None

    #
    # Reading data
    #

    def read(
        self,
        allow_squeezed: bool = True,
        apply_filters: bool = True,
        return_reader: bool = False,
    ):
        """Return the data object for this measurement.

        For height data this is a
        `SurfaceTopography.Topography`/`UniformLineScan`/`NonuniformLineScan`
        instance, guaranteed to

        - have a 'unit' property
        - have a size: .physical_sizes
        - have been scaled and detrended with the saved parameters

        It has not necessarily a pipeline with all these steps
        and a 'detrend_mode` attribute.

        This is only always the case
        if allow_squeezed=False. In this case the returned instance
        was regenerated from the original file with additional steps
        applied.

        If allow_squeezed=True, the returned instance may be read
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
            If True, return a tuple containing the data object and the reader.
            (Default: False)
        """
        return self.get_type().read(
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
        metadata = dict(self.metadata or {})

        # A height scale that the data file itself encodes must not be exported:
        # importing the archive would read the factor from the file *and* find it
        # in the metadata, applying it twice (see GH 718). Whether the file
        # provides it is exactly what `height_scale_editable` records.
        try:
            file_provides_height_scale = not getattr(
                self.info, "height_scale_editable", True
            )
        except MeasurementRegistryError:
            file_provides_height_scale = False
        if file_provides_height_scale:
            metadata.pop("height_scale", None)

        result = {
            "name": self.name,
            "datafile": {
                "original": self.datafile.filename,
                "squeezed-netcdf": (
                    self.squeezed_datafile.filename if self.squeezed_datafile_id else None
                ),
            },
            "kind": self.kind,
            "metadata": metadata,
            "channel": (
                None
                if self.channel_name is None
                else {
                    "name": self.channel_name,
                    "occurrence": self.channel_occurrence,
                }
            ),
            "created_by": {"name": self.created_by.name,
                           "orcid": getattr(self.created_by, 'orcid_id', None)},
            "measurement_date": self.measurement_date,
            "description": self.description,
            "tags": [t.name for t in self.tags.order_by("name")],
        }

        return result

    def deepcopy(self, to_surface):
        """Creates a copy of this measurement with all data files copied.

        Parameters
        ----------
        to_surface: Surface
            target surface

        Returns
        -------
        The copied measurement.
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
        # original measurement
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

    #
    # Derived artifacts
    #
    # The measurement type generates these; the error policy (log and store
    # nothing, rather than failing the whole inspection) is generic and lives
    # here.
    #

    def _make_derived(
        self, method, field, exception_class, data, none_on_error, save=False
    ):
        """
        Let the measurement type generate one derived artifact.

        On failure the corresponding field is cleared and the error logged, so
        that a measurement with, say, an unrenderable thumbnail still finishes
        its inspection. Callers that want to handle the failure themselves pass
        ``none_on_error=False``.

        Parameters
        ----------
        method : str
            Name of the measurement type's method that generates the artifact.
        field : str
            Field on this model that holds the artifact.
        exception_class : type
            Exception to raise when `none_on_error` is False.
        data : object
            Already loaded data object.
        none_on_error : bool
            Whether to swallow a failure and clear `field`.
        save : bool, optional
            Whether to save on success. (Default: False)
        """
        try:
            getattr(self.get_type(), method)(self, data)
        except Exception as exc:
            if not none_on_error:
                raise exception_class(self, str(exc)) from exc
            setattr(self, field, None)
            self.save(update_fields=[field])
            _log.error(
                "Problems while generating %s for measurement %s: %s. Saving <None> "
                "instead.",
                field,
                self.id,
                exc,
                exc_info=True,
            )
        else:
            if save:
                self.save()

    def make_thumbnail(self, none_on_error=True, st_topo=None):
        """Renew thumbnail field.

        Parameters
        ----------
        none_on_error: bool
            If True (default), sets thumbnail to None if there are any errors.
            If False, exceptions have to be caught outside.
        st_topo: data object, optional
            Already loaded data, to avoid reading the file again.

        Returns
        -------
        None

        Raises
        ------
        ThumbnailGenerationException
        """
        if st_topo is None:
            st_topo = self.read()
        self._make_derived(
            "make_thumbnail", "thumbnail", ThumbnailGenerationException, st_topo,
            none_on_error,
        )

    def make_deepzoom(self, none_on_error=True, st_topo=None):
        """Renew deep zoom image files.

        Parameters
        ----------
        none_on_error: bool
            If True (default), do not raise an exception if there are any errors.
            If False, exceptions have to be caught outside.
        st_topo: data object, optional
            Already loaded data, to avoid reading the file again.

        Returns
        -------
        None

        Raises
        ------
        DZIGenerationException
        """
        if not self.get_type().has_deepzoom:
            return
        if st_topo is None:
            st_topo = self.read()
        self._make_derived(
            "make_deepzoom", "deepzoom", DZIGenerationException, st_topo,
            none_on_error,
        )

    def make_squeezed(self, none_on_error=True, st_topo=None, save=False):
        """Renew the canonical ("squeezed") representation of the data.

        Parameters
        ----------
        none_on_error: bool
            If True (default), do not raise an exception if there are any errors.
            If False, exceptions have to be caught outside.
        st_topo: data object, optional
            Already loaded data, to avoid reading the file again.
        save: bool, optional
            Whether to save the measurement afterwards. (Default: False)
        """
        if not self.get_type().has_canonical_file:
            return
        if st_topo is None:
            st_topo = self.read(allow_squeezed=False)
        self._make_derived(
            "make_canonical_file", "squeezed_datafile",
            SqueezedDatafileGenerationException, st_topo, none_on_error, save=save,
        )

    def notify_users(self, sender, verb, description):
        self.permissions.notify_users(sender, verb, description)

    #
    # Inspection
    #

    def _select_channel(self, inspection):
        """
        Determine which channel of the data file this measurement refers to.

        Returns the channel's index. On the first inspection the reader's default
        channel is used (or the index recorded by an import of a container that
        predates named channels); afterwards the recorded name is resolved, and a
        name that no longer identifies exactly one channel is an error rather
        than a silent fallback.
        """
        if self.channel_name is not None:
            return inspection.resolve(self.channel_name, self.channel_occurrence)
        if self.channel_index_hint is not None:
            index = self.channel_index_hint
            if 0 <= index < len(inspection.channels):
                return index
            _log.warning(
                "Measurement %s records channel index %s, which the data file "
                "does not have; falling back to the default channel.",
                self.id,
                index,
            )
        return inspection.default_index

    def refresh_cache(self, timer=None):
        """
        Inspect the data file and renew cached properties.

        Determines the kind of measurement from the selected channel, merges the
        metadata the file provides into the stored metadata, refreshes the
        file-derived cache and regenerates the derived artifacts.
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
                    f"Measurement {self.id} does not appear to have a data file. "
                    f"Cannot refresh cached data."
                )

        _log.info(f"Caching properties of measurement {self.id}...")

        # Open the data file through whichever measurement type can read it.
        with timer("sniff_measurement_file"):
            inspection = sniff_measurement_file(self)

        # Idiot check
        if len(inspection.channels) == 0:
            raise RuntimeError(
                f"Datafile of measurement '{self.name}' could be opened, but it "
                "appears to contain no valid data."
            )

        channel_index = self._select_channel(inspection)
        channel = inspection.channels[channel_index]

        if channel.kind is None:
            raise UnsupportedChannelError(
                channel.name,
                "No measurement type is registered that can import it.",
            )

        measurement_type = get_measurement_type(channel.kind)

        # Everything up to here has left `self` untouched, and `inspect` does not
        # mutate it either. That matters for the rejection below: a file we refuse
        # must not leave a half-updated record behind, because a changed
        # significant field would re-dispatch the task on the terminal save().
        with timer("inspect"):
            result = measurement_type.inspect(self, inspection, channel_index)

        # Reject files with incomplete metadata if this instance is configured to
        # do so. The file is of a supported format and could be read, but the
        # metadata required to process it (physical size, unit) is missing and
        # would normally have to be entered manually through the UI. A field is
        # considered missing only if neither the file nor the existing metadata
        # provides it, so container/zip imports (which populate this metadata
        # from `index.json` before inspection) are not affected.
        if getattr(settings, "TOPOBANK_REJECT_INCOMPLETE_METADATA", False):
            missing = result.metadata.missing_metadata()
            if missing:
                raise IncompleteMetadataError(
                    f"The file format '{inspection.format}' is supported, but the "
                    f"file does not contain complete metadata. The following required "
                    f"metadata could not be read from the file: {', '.join(missing)}. "
                    f"This instance is configured to reject files with incomplete "
                    f"metadata."
                )

        #
        # Apply the result of the inspection.
        #
        if result.measurement_date is not None:
            self.measurement_date = result.measurement_date
        self.datafile_format = inspection.format
        self.kind = channel.kind
        self.channel_name = channel.name
        self.channel_occurrence = inspection.occurrence_for(channel_index)
        self.channel_index_hint = None
        self.metadata = dump_metadata(result.metadata)
        file_info = result.file_info

        # Read the file if metadata information is complete
        if self.is_metadata_complete:
            with timer("metadata is complete"):
                _log.info(f"Metadata of {self} is complete. Generating images.")
                with timer("read"):
                    data = measurement_type.read_from_inspection(self, inspection)

                # Refresh cached quantities that require the data itself, e.g.
                # bandwidths and whether the data has undefined points.
                with timer("refresh_derived_cache"):
                    measurement_type.refresh_derived_cache(self, data, file_info)
                self.file_info = dump_metadata(file_info)

                with timer("make_thumbnail"):
                    self.make_thumbnail(st_topo=data)
                with timer("make_deepzoom"):
                    self.make_deepzoom(st_topo=data)
                with timer("make_squeezed"):
                    self.make_squeezed(st_topo=data)

                # Verify the derived files actually landed. A measurement with
                # complete metadata is expected to have these; a missing one is
                # a silent data-quality failure that would otherwise be masked
                # by task_state=SUCCESS. We only log (generation stays
                # non-fatal) so monitoring can catch it.
                missing = []
                if self.thumbnail is None or not self.thumbnail.exists():
                    missing.append("thumbnail")
                if measurement_type.has_deepzoom and (
                    self.deepzoom is None or len(self.deepzoom) == 0
                ):
                    missing.append("deepzoom")
                if measurement_type.has_canonical_file and (
                    self.squeezed_datafile is None
                    or not self.squeezed_datafile.exists()
                ):
                    missing.append("squeezed_datafile")
                if missing:
                    _log.error(
                        "refresh_cache: measurement %s has complete metadata but "
                        "is missing derived files: %s",
                        self.id,
                        ", ".join(missing),
                    )
        else:
            self.file_info = dump_metadata(file_info)

        # Save dataset
        self.save()

        # Send signal
        _log.debug(f"Sending `post_refresh_cache` signal from {self}...")
        post_refresh_cache.send(sender=Measurement, instance=self)

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
