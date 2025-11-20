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

from ..analysis.models import (
    Workflow,
    WorkflowResult,
    WorkflowSubject,
    WorkflowTemplate,
)
from ..manager.models import Surface, Tag, Topography
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
        exclude = (
            "user",
            "allow",
        )
        skip_postgeneration_save = True

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
    permissions = factory.LazyAttribute(
        lambda obj: obj.folder.permissions if getattr(obj, "folder", None) is not None else None
    )
    confirmed_at = factory.LazyFunction(timezone.now)

    @post_generation
    def upload_file(obj, create, value, **kwargs):
        obj.save_file(File(open(f"{FIXTURE_DATA_DIR}/{obj.filename}", "rb")))


class FolderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "files.Folder"
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


class Topography1DFactory(factory.django.DjangoModelFactory):
    """
    Generates a 1D Topography.
    """

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = Topography
        exclude = ("filename",)
        skip_postgeneration_save = True

    permissions = factory.SelfAttribute("surface.permissions")
    surface = factory.SubFactory(SurfaceFactory)
    # created_by is set automatically to surface's created_by if not set, see signals
    name = factory.Sequence(lambda n: "topography-{:05d}".format(n))
    filename = "line_scan_1.asc"
    datafile = factory.SubFactory(
        ManifestFactory, filename=factory.SelfAttribute("..filename")
    )
    data_source = 0
    measurement_date = factory.Sequence(
        lambda n: datetime.date(2019, 1, 1) + datetime.timedelta(days=n)
    )
    size_x = 512
    # if you need size_y, use Topography2DFactory below
    size_editable = False
    unit_editable = False
    height_scale_editable = True
    unit = "nm"
    instrument_name = ""
    instrument_type = Topography.INSTRUMENT_TYPE_UNDEFINED
    instrument_parameters = {}

    @factory.post_generation
    def post_generation(self, create, value, **kwargs):
        self.datafile.permissions = self.permissions
        self.datafile.save()
        self.refresh_cache()


class Topography2DFactory(Topography1DFactory):
    """
    Generates a 2D Topography.
    """

    class Meta:
        model = Topography
        exclude = ("filename",)

    size_y = 512
    filename = "10x10.txt"
    datafile = factory.SubFactory(
        ManifestFactory, filename=factory.SelfAttribute("..filename")
    )

    @factory.post_generation
    def post_generation(self, create, value, **kwargs):
        self.datafile.permissions = self.permissions
        self.datafile.save()
        self.refresh_cache()


#
# Define factories for creating test objects
#
class WorkflowFactory(factory.django.DjangoModelFactory):
    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = Workflow

    name = factory.Sequence(lambda n: "Test Function no. {}".format(n))


def _analysis_result(analysis):
    if analysis.folder is not None:
        return analysis.function.eval(analysis)
    else:
        return {"test_result": 1.23}


def _failed_analysis_result(analysis):
    return {"message": "This analysis has failed."}


def _analysis_default_kwargs(analysis):
    return analysis.function.get_default_kwargs()


class AnalysisSubjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WorkflowSubject


class AnalysisFactoryWithoutResult(factory.django.DjangoModelFactory):
    """Abstract factory class for generating Analysis.

    For real analyses for Topographies or Surfaces use the
    child classes.
    """

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = WorkflowResult
        exclude = (
            "subject_topography",
            "subject_surface",
            "subject_tag",
            "subject",
            "user",
        )
        skip_postgeneration_save = True

    subject_topography = None  # factory.SubFactory(Topography2DFactory)
    subject_surface = None
    subject_tag = None

    user = factory.LazyAttribute(
        lambda obj: (
            obj.subject_surface.created_by
            if obj.subject_surface
            else (
                obj.subject_topography.created_by
                if obj.subject_topography
                else obj.subject_tag.get_related_surfaces().first().created_by
            )
        )
    )

    permissions = factory.SubFactory(
        PermissionSetFactory, user=factory.SelfAttribute("..user"), allow="view"
    )
    function = factory.SubFactory(WorkflowFactory)
    subject_dispatch = factory.SubFactory(
        AnalysisSubjectFactory,
        topography=factory.SelfAttribute("..subject_topography"),
        surface=factory.SelfAttribute("..subject_surface"),
        tag=factory.SelfAttribute("..subject_tag"),
    )
    subject = factory.LazyAttribute(
        lambda obj: (
            obj.subject_surface
            if obj.subject_surface
            else (obj.subject_topography if obj.subject_topography else obj.subject_tag)
        )
    )

    folder = factory.SubFactory(
        FolderFactory,
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
            "subject_topography",
            "subject_surface",
            "subject_tag",
            "subject",
            "user",
            "import_from_folder",
        )

    kwargs = factory.LazyAttribute(_analysis_default_kwargs)
    result = factory.LazyAttribute(_analysis_result)


class TopographyAnalysisFactory(AnalysisFactory):
    """Create an analysis for a topography."""

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = WorkflowResult

    subject_topography = factory.SubFactory(Topography2DFactory)


class FailedTopographyAnalysisFactory(AnalysisFactory):
    """Create an analysis for a topography."""

    # noinspection PyMissingOrEmptyDocstring
    class Meta:
        model = WorkflowResult

    subject_topography = factory.SubFactory(Topography2DFactory)
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


class WorkflowTemplateFactory(factory.django.DjangoModelFactory):
    """
    Factory for generating WorkflowTemplate instances.
    """

    class Meta:
        model = WorkflowTemplate

    name = factory.Sequence(lambda n: f"Workflow Template {n}")
    kwargs = {"param1": "value1", "param2": "value2"}  # Example JSON field
    implementation = factory.SubFactory(WorkflowFactory)
    created_by = factory.SubFactory(UserFactory)
    permissions = factory.SubFactory(
        PermissionSetFactory, user=factory.SelfAttribute("..created_by")
    )
