import datetime
import glob
import logging
import os

import factory
from django.core.files import File
from django.db import models
from django.db.models.signals import post_save
from django.utils import timezone
from factory import post_generation

from ..analysis.models import Workflow, WorkflowResult
from ..manager.models import Measurement, Surface, Tag
from ..measurements.registry import get_measurement_type
from ..measurements.schemas import dump_metadata
from ..measurements.types import (
    NonuniformLineScanType,
    TopographyMapType,
    UniformLineScanType,
)
from ..properties.models import Property
from .data import FIXTURE_DATA_DIR

_log = logging.getLogger(__name__)


class OrcidSocialAccountFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "socialaccount.SocialAccount"
        skip_postgeneration_save = True

    user_id = 0  # overwrite on construction
    provider = "orcid"
    uid = factory.Sequence(lambda n: "{:04d}-{:04d}-{:04d}-{:04d}".format(n, n, n, n))
    extra_data = {}

    @factory.post_generation
    def set_extra_data(self, create, value, **kwargs):
        self.extra_data = {
            "orcid-identifier": {
                "uri": "https://orcid.org/{}".format(self.uid),
                "path": self.uid,
                "host": "orcid.org",
            }
        }
        models.Model.save(self)


class UserFactory(factory.django.DjangoModelFactory):
    username = factory.Sequence(lambda n: f"user-{n}")
    email = factory.Sequence(lambda n: f"user-{n}@example.com")
    password = factory.PostGenerationMethodCall("set_password", "password")
    name = factory.Sequence(lambda n: f"name-{n}")

    class Meta:
        model = "users.User"
        django_get_or_create = ("username",)
        # NOTE: fix for factory_boy deprecation warning
        skip_postgeneration_save = True

    @factory.post_generation
    def create_orcid_account(self, create, value, **kwargs):
        OrcidSocialAccountFactory(user_id=self.id)
        # NOTE: tests break without this save
        models.Model.save(self)


class OrganizationFactory(factory.django.DjangoModelFactory):
    name = factory.Sequence(lambda n: f"organization-{n}")

    class Meta:
        model = "organizations.Organization"
        django_get_or_create = ("name",)


@factory.django.mute_signals(post_save)
class UserPermissionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "authorization.UserPermission"

    user = factory.SubFactory(UserFactory)
    allow = "full"


@factory.django.mute_signals(post_save)
class PermissionSetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "authorization.PermissionSet"
        skip_postgeneration_save = True
        exclude = (
            "user",
            "allow",
        )

    user = factory.SubFactory(UserFactory)
    allow = "full"
    permissions = factory.RelatedFactory(
        UserPermissionFactory,
        factory_related_name="parent",
        user=factory.SelfAttribute("..user"),
        allow=factory.SelfAttribute("..allow"),
    )


class ManifestFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "files.Manifest"
        skip_postgeneration_save = True

    filename = factory.Iterator(
        ["10x10.txt", "dektak-1.csv", "example.opd", "example3.di", "plux-1.plux"]
    )
    permissions = None
    confirmed_at = factory.LazyFunction(timezone.now)

    @factory.post_generation
    def folder(obj, create, extracted, **kwargs):
        if extracted is not None and create:
            obj.folder = extracted
            update_fields = ["folder"]
            if obj.permissions is None:
                obj.permissions = extracted.permissions
                update_fields.append("permissions")
            obj.save(update_fields=update_fields)

    @post_generation
    def upload_file(obj, create, value, **kwargs):
        obj.save_file(File(open(f"{FIXTURE_DATA_DIR}/{obj.filename}", "rb")))


class ManifestSetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "files.ManifestSet"
        exclude = ("user",)

    read_only = True

    user = factory.SubFactory(UserFactory)
    permissions = factory.SubFactory(
        PermissionSetFactory,
        user=factory.SelfAttribute("..user"),
    )


#
# Define factories for creating test objects
#
class SurfaceFactory(factory.django.DjangoModelFactory):
    """Generates a Surface."""

    class Meta:
        model = Surface

    name = factory.Sequence(
        lambda n: "surface-{:05d}".format(n)
    )  # format because of defined order by name
    created_by = factory.SubFactory(UserFactory)
    permissions = factory.SubFactory(
        PermissionSetFactory, user=factory.SelfAttribute("..created_by")
    )


class TagFactory(factory.django.DjangoModelFactory):
    """Generates a Tag."""

    class Meta:
        model = Tag
        skip_postgeneration_save = True

    name = factory.Sequence(lambda n: "tag-{:05d}".format(n))

    @factory.post_generation
    def surfaces(self, create, extracted, **kwargs):
        if not create:
            # Simple build, do nothing
            return
        if extracted:
            # A list of surfaces were passed in, use them for the manytomany field
            for surface in extracted:
                self.surface_set.add(surface)


class PropertyFactory(factory.django.DjangoModelFactory):
    """Generates a Property."""

    class Meta:
        model = Property

    @factory.post_generation
    def surfaces(self, create, extracted, **kwargs):
        if not create:
            # Simple build, do nothing
            return
        if extracted:
            # A list of surfaces were passed in, use them for the manytomany field
            for surface in extracted:
                self.properties.add(surface)


#: Factory keyword arguments that belong to the file-derived cache
#: (``Measurement.file_info``) rather than to the user-facing metadata.
_FILE_INFO_KEYS = frozenset(
    {
        "size_editable",
        "unit_editable",
        "height_scale_editable",
        "is_periodic_editable",
        "resolution_x",
        "resolution_y",
        "bandwidth_lower",
        "bandwidth_upper",
        "short_reliability_cutoff",
        "has_undefined_data",
        "undefined_data_fraction",
        "detrend_parameters",
        "channels",
    }
)

#: Convenience aliases for the nested instrument metadata, so tests can keep
#: passing them flat.
_INSTRUMENT_KEYS = {
    "instrument_name": "name",
    "instrument_type": "type",
    "instrument_parameters": "parameters",
}


class MeasurementFactory(factory.django.DjangoModelFactory):
    """
    Base factory for measurements.

    Metadata lives in JSON documents on the model, but writing that out in every
    test would be noise. This factory therefore accepts the metadata fields of its
    kind as flat keyword arguments (``size_x=512``, ``unit="nm"``, ...) and packs
    them into ``metadata``; keys belonging to the file-derived cache go into
    ``file_info``. Everything is validated through the kind's pydantic schemas, so
    a typo or a field that does not apply to the kind fails here rather than
    silently ending up in the wrong place.
    """

    class Meta:
        model = Measurement
        exclude = ("filename",)
        skip_postgeneration_save = True
        abstract = True

    permissions = factory.SelfAttribute("surface.permissions")
    surface = factory.SubFactory(SurfaceFactory)
    # Set created_by explicitly from surface's created_by
    created_by = factory.SelfAttribute("surface.created_by")
    name = factory.Sequence(lambda n: "measurement-{:05d}".format(n))
    measurement_date = factory.Sequence(
        lambda n: datetime.date(2019, 1, 1) + datetime.timedelta(days=n)
    )
    # `post_generation` below calls refresh_cache(), which is the body of the
    # inspection task (see Measurement.task_worker). Calling it directly bypasses
    # the task wrapper that would normally record the outcome, so factory-built
    # measurements would otherwise look like they were never inspected
    # successfully despite having a populated cache. Override to build a
    # measurement in a different state, e.g. task_state=Measurement.FAILURE.
    task_state = Measurement.SUCCESS

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        kind = kwargs.get("kind")
        measurement_type = get_measurement_type(kind)
        metadata = dict(kwargs.pop("metadata", None) or {})
        file_info = dict(kwargs.pop("file_info", None) or {})
        instrument = dict(metadata.pop("instrument", None) or {})

        for key in list(kwargs):
            if key in _FILE_INFO_KEYS:
                file_info[key] = kwargs.pop(key)
            elif key in _INSTRUMENT_KEYS:
                instrument[_INSTRUMENT_KEYS[key]] = kwargs.pop(key)
            elif key != "kind" and key in measurement_type.Metadata.model_fields:
                metadata[key] = kwargs.pop(key)

        if instrument:
            metadata["instrument"] = instrument
        metadata["kind"] = kind
        file_info["kind"] = kind

        kwargs["metadata"] = dump_metadata(measurement_type.Metadata(**metadata))
        kwargs["file_info"] = dump_metadata(measurement_type.FileInfo(**file_info))
        return super()._create(model_class, *args, **kwargs)

    @factory.post_generation
    def post_generation(self, create, value, **kwargs):
        self.datafile.permissions = self.permissions
        self.datafile.save()
        requested_task_state = self.task_state
        self.refresh_cache()
        # Saving the datafile and refreshing the cache re-dispatch the inspection
        # task, which resets task_state to PENDING. Restore the requested state,
        # bypassing signals so it is not reset again. All these factories set
        # `skip_postgeneration_save`, so the instance is not written again after
        # this; writing it both in memory and in the database keeps the two
        # consistent either way.
        self.task_state = requested_task_state
        Measurement.objects.filter(pk=self.pk).update(task_state=requested_task_state)


class NonuniformLineScanFactory(MeasurementFactory):
    """
    Generates a line scan with non-uniformly spaced points.

    Note that this kind has neither `is_periodic` nor `fill_undefined_data_mode`:
    a nonuniform line scan supports neither, so its schema has no such fields and
    passing them here is an error.
    """

    class Meta:
        model = Measurement
        exclude = ("filename",)
        skip_postgeneration_save = True

    kind = NonuniformLineScanType.Meta.name
    filename = "line_scan_1.asc"
    datafile = factory.SubFactory(
        ManifestFactory, filename=factory.SelfAttribute("..filename")
    )
    size_x = 512
    # if you need size_y, use TopographyMapFactory below
    size_editable = False
    unit_editable = False
    height_scale_editable = True
    unit = "nm"


class UniformLineScanFactory(MeasurementFactory):
    """Generates a line scan on a uniform grid."""

    class Meta:
        model = Measurement
        exclude = ("filename",)
        skip_postgeneration_save = True

    kind = UniformLineScanType.Meta.name
    filename = "example6.txt"
    datafile = factory.SubFactory(
        ManifestFactory, filename=factory.SelfAttribute("..filename")
    )
    size_editable = False
    unit_editable = False
    height_scale_editable = True


class TopographyMapFactory(MeasurementFactory):
    """Generates a two-dimensional map of surface heights."""

    class Meta:
        model = Measurement
        exclude = ("filename",)
        skip_postgeneration_save = True

    kind = TopographyMapType.Meta.name
    filename = "10x10.txt"
    datafile = factory.SubFactory(
        ManifestFactory, filename=factory.SelfAttribute("..filename")
    )
    size_x = 512
    size_y = 512
    size_editable = False
    unit_editable = False
    height_scale_editable = True
    unit = "nm"


#
# Define factories for creating test objects
#
def _analysis_result(analysis):
    if analysis.folder is not None:
        return Workflow(name=analysis.workflow_name).eval(analysis)
    else:
        return {"test_result": 1.23}


def _failed_analysis_result(analysis):
    return {"message": "This analysis has failed."}


def _analysis_default_kwargs(analysis):
    return Workflow(name=analysis.workflow_name).get_default_kwargs()


class AnalysisFactoryWithoutResult(factory.django.DjangoModelFactory):
    """Abstract factory class for generating Analysis.

    For real analyses for Topographies or Surfaces use the
    child classes.
    """

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = WorkflowResult
        exclude = (
            "user",
            "subject",  # computed proxy for eval during factory build; not a model field
        )
        skip_postgeneration_save = True

    subject_measurement = None  # factory.SubFactory(TopographyMapFactory)
    subject_surface = None
    subject_tag = None

    # Proxy so that Workflow.eval() can call analysis.subject during factory build
    subject = factory.LazyAttribute(
        lambda obj: (
            obj.subject_surface
            if obj.subject_surface
            else (obj.subject_measurement if obj.subject_measurement else obj.subject_tag)
        )
    )

    user = factory.LazyAttribute(
        lambda obj: (
            obj.subject_surface.created_by
            if obj.subject_surface
            else (
                obj.subject_measurement.created_by
                if obj.subject_measurement
                else obj.subject_tag.get_related_surfaces().first().created_by
            )
        )
    )

    # Store user for later use
    created_by = factory.LazyAttribute(lambda obj: obj.user)

    permissions = factory.SubFactory(
        PermissionSetFactory, user=factory.SelfAttribute("..user"), allow="view"
    )
    workflow_name = "topobank.testing.test"

    folder = factory.SubFactory(
        ManifestSetFactory,
        permissions=factory.SelfAttribute("..permissions"),
        read_only=True,
    )

    task_state = WorkflowResult.SUCCESS

    task_submission_time = factory.LazyFunction(timezone.now)
    task_start_time = factory.LazyFunction(
        lambda: timezone.now() - datetime.timedelta(0, 1)
    )
    task_end_time = factory.LazyFunction(timezone.now)

    @factory.post_generation
    def import_folder(obj, create, value, **kwargs):
        if "name" in kwargs:
            for fn in glob.glob(f"{kwargs['name']}/*"):
                obj.folder.save_file(os.path.basename(fn), "der", File(open(fn, "rb")))
            obj.kwargs = obj.folder.read_json("model.json")["kwargs"]
            models.Model.save(obj)


class AnalysisFactory(AnalysisFactoryWithoutResult):
    class Meta:
        model = WorkflowResult
        exclude = (
            "user",
            "subject",
            "import_from_folder",
        )

    kwargs = factory.LazyAttribute(_analysis_default_kwargs)
    result = factory.LazyAttribute(_analysis_result)


class MeasurementAnalysisFactory(AnalysisFactory):
    """Create an analysis for a topography."""

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = WorkflowResult

    subject_measurement = factory.SubFactory(TopographyMapFactory)


class FailedMeasurementAnalysisFactory(AnalysisFactory):
    """Create an analysis for a topography."""

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = WorkflowResult

    subject_measurement = factory.SubFactory(TopographyMapFactory)
    result = factory.LazyAttribute(_failed_analysis_result)


class SurfaceAnalysisFactory(AnalysisFactory):
    """Create an analysis for a surface."""

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = WorkflowResult

    subject_surface = factory.SubFactory(SurfaceFactory)


class TagAnalysisFactory(AnalysisFactory):
    """Create an analysis for a surface collection."""

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = WorkflowResult

    subject_tag = factory.SubFactory(TagFactory)
