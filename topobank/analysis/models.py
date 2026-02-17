"""
Models related to analyses.
"""

import json
import logging
from functools import partial
from typing import Union
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import models, transaction
from django.db.models import Q
from django.urls import resolve
from django.urls.exceptions import Resolver404
from rest_framework.exceptions import PermissionDenied
from rest_framework.reverse import reverse

from topobank.authorization.permissions import EDIT, FULL
from topobank.organizations.models import Organization

from ..authorization.mixins import PermissionMixin
from ..authorization.models import AuthorizedManager, PermissionSet, ViewEditFull
from ..files.models import Folder, Manifest
from ..manager.models import Surface, Tag, Topography
from ..supplib.dict import load_split_dict, store_split_dict
from ..taskapp.models import Configuration, TaskStateModel
from .registry import WorkflowNotImplementedException, get_implementation

_log = logging.getLogger(__name__)

RESULT_FILE_BASENAME = "result"


class AnalysisSubjectManager(models.Manager):
    def create(self, subject=None, *args, **kwargs):
        if subject:
            if isinstance(subject, Tag):
                kwargs["tag"] = subject
            elif isinstance(subject, Topography):
                kwargs["topography"] = subject
            elif isinstance(subject, Surface):
                kwargs["surface"] = subject
            else:
                raise ValueError(
                    "`subject` argument must be of type `Tag`, `Topography` or "
                    "`Surface`."
                )
        return super().create(*args, **kwargs)


class WorkflowSubject(models.Model):
    """WorkflowResult subject, which can be either a Tag, a Topography or a Surface"""

    objects = AnalysisSubjectManager()

    tag = models.ForeignKey(Tag, null=True, blank=True, on_delete=models.CASCADE)
    topography = models.ForeignKey(
        Topography, null=True, blank=True, on_delete=models.CASCADE
    )
    surface = models.ForeignKey(
        Surface, null=True, blank=True, on_delete=models.CASCADE
    )

    class Meta:
        indexes = [
            models.Index(
                fields=['topography', 'surface', 'tag'],
                name='subject_topo_surf_tag_idx',
            ),
        ]

    @staticmethod
    def Q(subject) -> models.Q:
        if isinstance(subject, Tag):
            return models.Q(subject_dispatch__tag_id=subject.id)
        elif isinstance(subject, Topography):
            return models.Q(subject_dispatch__topography_id=subject.id)
        elif isinstance(subject, Surface):
            return models.Q(subject_dispatch__surface_id=subject.id)
        else:
            raise ValueError(
                "`subject` argument must be of type `Tag`, `Topography` or `Surface`, "
                f"not {type(subject)}."
            )

    @staticmethod
    def Qs(user, subjects) -> models.Q | None:
        """
        Build a Q object to filter WorkflowResults for multiple subjects.

        Parameters
        ----------
        user : User
            The user for permission filtering (applied to tag-based results)
        subjects : list
            List of Tag, Topography, or Surface instances

        Returns
        -------
        django.db.models.Q or None
            Combined query object for filtering WorkflowResults
        """
        tag_ids = []
        topography_ids = []
        surface_ids = []

        for subject in subjects:
            if isinstance(subject, Tag):
                tag_ids.append(subject.id)
            elif isinstance(subject, Topography):
                topography_ids.append(subject.id)
            elif isinstance(subject, Surface):
                surface_ids.append(subject.id)
            else:
                raise ValueError(
                    "`subject` argument must be of type `Tag`, `Topography` or `Surface`, "
                    f"not {type(subject)}."
                )

        query = None

        # Build query for tags (with user permission filtering)
        if tag_ids:
            q = models.Q(subject_dispatch__tag_id__in=tag_ids) & Q(
                permissions__user_permissions__user=user
            )
            query = q

        # Build query for topographies
        if topography_ids:
            q = models.Q(subject_dispatch__topography_id__in=topography_ids)
            query = query | q if query else q

        # Build query for surfaces
        if surface_ids:
            q = models.Q(subject_dispatch__surface_id__in=surface_ids)
            query = query | q if query else q

        return query

    def get(self):
        if self.tag is not None:
            return self.tag
        elif self.topography is not None:
            return self.topography
        elif self.surface is not None:
            return self.surface
        else:
            raise RuntimeError(
                "Database corruption: All subjects appear to be None/null."
            )

    def get_type(self):
        return self.get().__class__

    def is_ready(self) -> bool:
        """Check whether the subject is in SUCCESS state."""
        subject = self.get()

        if isinstance(subject, Tag):
            # For tags, check all tagged topographies
            # (only topographies have task states; surfaces are always ready)
            topographies = Topography.objects.filter(tags=subject)

            for topo in topographies:
                if hasattr(topo, "get_task_state"):
                    if topo.get_task_state() != topo.SUCCESS:
                        return False

            return True

        elif hasattr(subject, "get_task_state"):
            # For Topography instances - check their task state
            return subject.get_task_state() == subject.SUCCESS
        else:
            # For Surface instances - no task state means always ready
            return True

    def save(self, *args, **kwargs):
        if (
            sum(
                [
                    self.tag is not None,
                    self.topography is not None,
                    self.surface is not None,
                ]
            )
            != 1
        ):
            raise ValidationError("Only of of tag, topography or tag can be defined.")
        super().save(*args, **kwargs)


class WorkflowResult(PermissionMixin, TaskStateModel):
    """
    This class represents the result of a Workflow. It refers to the actual
    implementation of the Workflow and subject of the Workflow and stores its output in
    a folder. There is additional metadata stored in the database, such as the time
    when the Workflow was run and information about the server configuration when the
    Workflow was run.
    """

    #
    # Manager
    #
    objects = AuthorizedManager()

    #
    # Permissions
    #
    permissions = models.ForeignKey(PermissionSet, on_delete=models.CASCADE, null=True)

    #
    # Workflow result parameters
    #

    # Actual implementation of the workflow result as a Python function
    function = models.ForeignKey(
        "analysis.Workflow", related_name="results", on_delete=models.SET_NULL, null=True
    )

    # Definition of the subject
    subject_dispatch = models.OneToOneField(
        WorkflowSubject, on_delete=models.CASCADE, null=True
    )

    # Unique, user-specified name
    name = models.TextField(null=True)

    # user-specified description
    description = models.TextField(
        null=True, blank=True, help_text="Optional description of the analysis."
    )

    # Keyword arguments passed to the Python workflow result function
    kwargs = models.JSONField(default=dict)

    # Metadata describing the report generation
    metadata = models.JSONField(default=dict, blank=True, null=True)

    # Dependencies
    dependencies = models.JSONField(default=dict)

    # Results
    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, null=True)

    # Bibliography
    dois = models.JSONField(default=list)

    # Server configuration (version information)
    configuration = models.ForeignKey(
        Configuration, null=True, on_delete=models.SET_NULL
    )

    # Timestamp of creation of this WorkflowResult instance
    created_at = models.DateTimeField(auto_now_add=True)

    # Last modification time
    updated_at = models.DateTimeField(auto_now=True)

    # Creator of this WorkflowResult instance
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )

    # Last user updating this WorkflowResult instance (removed reverse relation)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    # Organization owning this WorkflowResult
    owned_by = models.ForeignKey(
        Organization, null=True, on_delete=models.CASCADE
    )

    # Invalid is True if the subject was changed after the WorkflowResult was computed
    deprecation_time = models.DateTimeField(null=True)

    class Meta:
        indexes = [
            # Index on task_start_time for ordering recent results
            models.Index(fields=['-task_start_time'], name='result_task_start_idx'),
            # Composite index for filtering by state and ordering by time
            # Used in: WHERE task_state = x ORDER BY task_start_time
            models.Index(fields=['task_state', '-task_start_time'], name='result_state_time_idx'),
            # Composite index for filtering by function and ordering by time
            # Used in: WHERE function = x ORDER BY task_start_time
            models.Index(fields=['function', '-task_start_time'], name='result_workflow_time_idx'),
            # Partial index for active (non-deprecated) results
            # Most common query pattern: active results ordered by time
            # Smaller than full index since it only includes non-deprecated rows
            models.Index(
                fields=['-task_start_time'],
                name='result_active_time_idx',
                condition=Q(deprecation_time__isnull=True)
            ),
            # Composite index for filtering by function + subject and ordering by time
            # Used in: WHERE function = x AND subject_dispatch = y ORDER BY task_start_time
            models.Index(
                fields=['function', 'subject_dispatch', '-task_start_time'],
                name='result_func_subj_time_idx',
            ),
        ]

    def __init__(self, *args, result=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._result = result  # temporary storage
        self._result_cache = result  # cached result
        self._result_metadata_cache = None  # cached toplevel result file

    def __str__(self):
        return (
            f"WorkflowResult {self.id} on subject {self.subject} with state {self.task_state}"
        )

    def save(self, *args, **kwargs):
        """
        Save the WorkflowResult instance to the database.

        This method performs the following steps:
        1. If the WorkflowResult has a name and a subject_dispatch, it removes the
           subject_dispatch to prevent cascade deletion when the subject is deleted.
        2. Calls the superclass's save method to persist the changes to the database and create
           the WorkflowResult instance if it is new.
        3. If a result dictionary was provided during initialization, it stores the result
           in the storage backend using the store_split_dict function and clears the
           temporary result storage.
        4. If a subject_dispatch was removed in step 1, it deletes the orphaned subject_dispatch
           instance from the database in a transaction-safe manner.

        Parameters
        ----------
        *args : tuple
            Variable length argument list.
        **kwargs : dict
            Arbitrary keyword arguments.
        """

        # Ensure permissions and folder are set
        if self.permissions is None:
            _log.debug(
                "WorkflowResult has no permissions. Attempting to create new permission set.")
            if self.created_by:
                self.permissions = PermissionSet.objects.create()
                self.permissions.grant(self.created_by, FULL)
            else:
                raise RuntimeError(
                    "WorkflowResult is missing permission set and created_by. Cannot create permissions."
                )
        if self.folder is None:
            self.folder = Folder.objects.create(
                permissions=self.permissions, read_only=True
            )
            if 'update_fields' in kwargs:
                if kwargs['update_fields'] is not None:
                    kwargs['update_fields'].append('folder')

        if not self.pk:
            # New instance - ensure creator has EDIT permission
            if self.created_by:
                self.permissions.grant(self.created_by, EDIT)
            else:
                # This should be an error, but v1 does not enforce it like v2 does
                _log.warning("WorkflowResult saved without created_by user set.")

        # If the analysis has a name, we remove the subject dispatch to prevent CASCADE deletion
        # when the subject (Tag/Topography/Surface) is deleted
        if self.name and self.subject_dispatch:
            self.subject_dispatch = None
            if 'update_fields' in kwargs:
                # If explicitly set to None, leave it (means update all fields in Django)
                if kwargs['update_fields'] is not None:
                    if 'subject_dispatch' not in kwargs['update_fields']:
                        kwargs['update_fields'].append('subject_dispatch')

        # If a result dict is given on input, we store it. However, we can only do
        # this once we have an id. This happens during testing.
        # TODO: Fix testing so that we do not need this workaround.
        super().save(*args, **kwargs)

        # We now have an id
        if self._result:
            store_split_dict(self.folder, RESULT_FILE_BASENAME, self._result)
            self._result = None

    @property
    def subject(self):
        """
        Return the subject of the WorkflowResult, which can be a Tag, a Topography, or a
        Surface.

        Returns
        -------
        Tag, Topography, or Surface
            The subject of the WorkflowResult.
        """
        if self.subject_dispatch:
            return self.subject_dispatch.get()
        else:
            return None

    @property
    def result(self):
        """
        Return the result object or None if there is nothing yet.

        This property checks if the result cache is empty. If it is, it loads the result
        from the storage backend using the storage prefix and result file basename.
        The loaded result is then cached for future access.

        Returns
        -------
        dict or None
            The result object if available, otherwise None.
        """
        self.fix_folder()
        if self._result_cache is None:
            self._result_cache = load_split_dict(self.folder, RESULT_FILE_BASENAME)
        return self._result_cache

    @property
    def result_metadata(self):
        """
        Return the toplevel result object without series data, i.e. the raw result.json
        without unsplitting it.

        This property checks if the result metadata cache is empty. If it is, it loads
        the metadata from the storage backend using the storage prefix and result file
        basename. The loaded metadata is then cached for future access.

        Returns
        -------
        dict
            The toplevel result object without series data.
        """
        self.fix_folder()
        if self._result_metadata_cache is None:
            self._result_metadata_cache = json.load(
                self.folder.open_file(f"{RESULT_FILE_BASENAME}.json")
            )
        return self._result_metadata_cache

    @property
    def result_file_name(self):
        """Returns name of the result file in storage backend as string."""
        return f"{RESULT_FILE_BASENAME}.json"

    @property
    def has_result_file(self):
        """Returns True if result file exists in storage backend, else False."""
        self.fix_folder()
        return self.folder.exists(self.result_file_name)

    def get_absolute_url(self, request=None):
        """URL of API endpoint for this tag"""
        return reverse(
            "analysis:result-detail", kwargs=dict(pk=self.id), request=request
        )

    @property
    def storage_prefix(self):
        """Return prefix used for storage.

        Looks like a relative path to a directory.
        If storage is on filesystem, the prefix should correspond
        to a real directory.
        """
        if self.id is None:
            raise RuntimeError(
                "This `WorkflowResult` does not have an id yet; the storage prefix is not "
                "yet known."
            )
        return "analyses/{}".format(self.id)

    def fix_folder(self):
        """
        Fill folder, if yet unfilled.

        List of files names ['<file_prefix_name>/file'].
        If storage is on filesystem, the prefix should correspond
        to a real directory.
        """
        if self.folder:
            return
        if self.id is None:
            raise RuntimeError(
                "This `WorkflowResult` does not have an id yet; the storage file names is "
                "not yet known."
            )
        self.folder = Folder.objects.create(
            permissions=self.permissions, read_only=True
        )
        self.save(update_fields=["folder"])
        dir_tuple = default_storage.listdir(self.storage_prefix)
        for filename in dir_tuple[1]:
            manifest = Manifest.objects.create(
                permissions=self.permissions,
                folder=self.folder,
                filename=filename,
                kind="der",
            )
            manifest.file.name = f"{self.storage_prefix}/{filename}"
            manifest.save(update_fields=["file"])

    def get_related_surfaces(self):
        """Returns sequence of surface instances related to the subject of this WorkflowResult."""
        return self.subject.get_related_surfaces()

    @property
    def implementation(self):
        return self.function.implementation

    def get_celery_queue(self) -> str:
        impl = self.implementation
        if hasattr(impl.Meta, "celery_queue") and impl.Meta.celery_queue is not None:
            # Implementation-specific queue
            return impl.Meta.celery_queue
        else:
            # Default queue for workflow result tasks
            return settings.TOPOBANK_ANALYSIS_QUEUE

    # FIXME: discuss whether to remove this method and use the generic one from PermissionMixin
    # overrides PermissionMixin.authorize_user <- this one returns nothing, raises exception on failure
    # v This one grants the user permission to access the WorkflowResult without permission.
    def authorize_user(self, user: settings.AUTH_USER_MODEL, access_level: ViewEditFull = "view"):
        """
        Returns an exception if given user should not be able to see this WorkflowResult.
        """
        # Check availability of workflow result function
        if not self.implementation.has_permission(user):
            raise PermissionDenied(
                f"User {user} is not allowed to use this WorkflowResult function."
            )

        super().authorize_user(user, access_level)

        # Disabling automatic permission granting to avoid unintended access
        # if self.is_tag_related:
        #     # Check if the user can access this WorkflowResult
        #     super().authorize_user(user, access_level)

        # # Check if user can access the subject of this WorkflowResult
        # self.subject.authorize_user(user, access_level)
        # self.grant_permission(user, access_level)  # Required so files can be accessed

    @property
    def is_topography_related(self) -> bool:
        """Returns True, if the WorkflowResult subject is a topography, else False."""
        return self.subject_dispatch.topography is not None

    @property
    def is_surface_related(self) -> bool:
        """Returns True, if the WorkflowResult subject is a surface, else False."""
        return self.subject_dispatch.surface is not None

    @property
    def is_tag_related(self) -> bool:
        """Returns True, if the WorkflowResult subject is a tag, else False."""
        return self.subject_dispatch.tag is not None

    def eval_self(self, **auxiliary_kwargs):
        if self.is_tag_related:
            users = self.permissions.user_permissions.all()
            if users.count() != 1:
                raise PermissionError(
                    "This is a tag WorkflowResult, which should only be assigned to a single "
                    "user."
                )
            self.subject.authorize_user(users.first().user, "view")

        return self.function.eval(
            self,
            **auxiliary_kwargs,
        )

    def submit(self, force_submit: bool = False) -> "WorkflowResult":
        with transaction.atomic():
            self.set_pending_state()
            transaction.on_commit(
                partial(submit_analysis_task_to_celery, self, force_submit)
            )
        return self

    def submit_again(self, force_submit: bool = True) -> "WorkflowResult":
        return self.submit(force_submit=force_submit)

    # v1 only
    def set_name(self, name: str, description: str = None):
        """
        Setting a name essentially saves the WorkflowResult, i.e. it is no longer deleted
        when the WorkflowResult subject is deleted.
        """
        self.name = name
        self.description = description
        self.subject_dispatch = None
        self.save(update_fields=["name", "description", "subject_dispatch"])


def submit_analysis_task_to_celery(analysis: WorkflowResult, force_submit: bool):
    """
    Send task to the queue after the WorkflowResult has been created. This is typically run
    in an on_commit hook. Note: on_commit will not execute in tests, unless
    transaction=True is added to pytest.mark.django_db
    """
    from .tasks import schedule_workflow

    # TODO: force_submit is currently hardcoded to True everywhere this is called.
    _log.debug(f"Submitting task for WorkflowResult {analysis.id}...")
    analysis.task_id = schedule_workflow.apply_async(
        args=[analysis.id, force_submit], queue=analysis.get_celery_queue()
    ).id
    analysis.save(update_fields=["task_id"])


class Workflow(models.Model):
    """
    A convenience wrapper around the WorkflowImplementation that has representation in
    the SQL database.
    """

    name = models.TextField(help_text="Internal unique identifier")
    display_name = models.TextField(help_text="Human-readable name")

    def __str__(self):
        return self.name

    @property
    def implementation(self):
        """Return implementation for given subject type.

        Returns
        -------
        AnalysisImplementation instance

        Raises
        ------
        ImplementationMissingException
            in case the implementation is missing
        """
        return get_implementation(name=self.name)

    def has_implementation(self, model_class):
        """
        Returns whether implementation function for a specific subject model exists
        """
        impl = self.implementation
        if impl is not None:
            return impl.has_implementation(model_class)
        return False

    def has_permission(self, user: settings.AUTH_USER_MODEL):
        """
        Check if this Workflow function is available to the user. The function
        is available to `user` if it is available for any of the `models`
        specified.
        """
        impl = self.implementation
        if impl is not None:
            return impl.has_permission(user)
        return False

    def get_default_kwargs(self):
        """
        Return default keyword arguments as a dictionary.
        """
        return self.implementation.Parameters().model_dump()

    def get_kwargs_schema(self):
        """
        JSON schema describing the keyword arguments.
        """
        return self.implementation.Parameters().model_json_schema()

    def get_outputs_schema(self) -> list:
        """
        JSON schema describing workflow outputs.

        Returns
        -------
        list
            List of file descriptors with their schemas
        """
        impl = self.implementation
        if impl is not None and hasattr(impl, "get_outputs_schema"):
            return impl.get_outputs_schema()
        return []

    def clean_kwargs(self, kwargs: Union[dict, None], fill_missing: bool = True):
        """
        Validate keyword arguments (parameters) and return validated dictionary

        Parameters
        ----------
        kwargs: Union[dict, None]
            Keyword arguments
        fill_missing: bool, optional
            Fill missing keys with default values. (Default: True)

        Raises
        ------
        pydantic.ValidationError if validation fails
        """
        return self.implementation.clean_kwargs(kwargs, fill_missing=fill_missing)

    def get_dependencies(self, analysis):
        return self.implementation(**analysis.kwargs).get_dependencies(analysis)

    def eval(self, analysis, **auxiliary_kwargs):
        """
        First argument is the subject of the WorkflowResult (`Surface`, `Topography` or `Tag`).
        """
        runner = self.implementation(**analysis.kwargs)
        return runner.eval(analysis, **auxiliary_kwargs)

    def submit(
        self,
        user: settings.AUTH_USER_MODEL,
        subject: Union[Tag, Surface, Topography],
        kwargs: dict = None,
        force_submit: bool = False,
    ):
        """
        user : topobank.users.models.User
            Users which should see the WorkflowResult.
        subject : Tag or Topography or Surface
            Instance which will be subject of the WorkflowResult (first argument of WorkflowResult
            function).
        kwargs : dict, optional
            Keyword arguments for the function which should be saved to database. If
            None is given, the default arguments for the given WorkflowResult function are
            used. The default arguments are the ones used in the function
            implementation (python function). (Default: None)
        force_submit : bool, optional
            Submit even if WorkflowResult already exists. (Default: False)
        """
        # Check if user can actually access the subject
        subject.authorize_user(user, "view")

        # Check whether there is an implementation for this Workflow/subject combination
        if not self.has_implementation(type(subject)):
            raise WorkflowNotImplementedException(self.name, type(subject))

        # FIXME!!! Weird things happen is a workflow is triggered before the dataset
        # is fully analyzed and in a SUCCESS state, but tests fail when this is enabled.
        # if hasattr(subject, "get_task_state"):
        #     # Make sure all tasks (e.g. refreshing caches) have completed
        #     if subject.get_task_state() != subject.SUCCESS:
        #         raise SubjectNotReadyException(subject)

        # Make sure the parameters are correct and fill in missing values
        # (will trigger validation error if not)
        kwargs = self.clean_kwargs(kwargs)

        # Query for all existing WorkflowResults with the same parameters
        q = WorkflowSubject.Q(subject) & Q(function=self) & Q(kwargs=kwargs)

        # If subject is tag, we need to restrict this to the current user because those
        # WorkflowResults cannot be shared
        if isinstance(subject, Tag):
            q &= Q(permissions__user_permissions__user=user)

        # All existing WorkflowResults for this subject and parameter set
        existing_analyses = WorkflowResult.objects.for_user(user).filter(q)

        # WorkflowResults, excluding those that have failed or that have not been submitted
        # to the task queue for some reason (state "no"t run)
        successful_or_running_analyses = existing_analyses.filter(
            task_state__in=[
                WorkflowResult.PENDING,
                WorkflowResult.PENDING_DEPENDENCIES,
                WorkflowResult.RETRY,
                WorkflowResult.STARTED,
                WorkflowResult.SUCCESS,
            ]
        )

        # We submit a new WorkflowResult only if we are either forced to do so or if there is
        # no WorkflowResult with the same parameter pending, running or successfully completed.
        if force_submit or successful_or_running_analyses.count() == 0:
            # Delete *all* existing WorkflowResults with this subject/parameter set
            # (which now may only contain failed ones),
            # excluding saved/named ones (name__isnull is a redundant since all saved
            # analyses no longer have subjects)
            existing_analyses.filter(name__isnull=True).delete()

            return self._submit_new_analysis(user, subject, kwargs)
        else:
            # There seem to be viable analyses. Fetch the latest one.
            analysis = existing_analyses.order_by("task_start_time").last()
            return analysis

    def _submit_new_analysis(
        self,
        user: settings.AUTH_USER_MODEL,
        subject: Union[Tag, Topography, Surface],
        kwargs: dict
    ):
        """
        Create and submit a new WorkflowResult analysis.

        Parameters
        ----------
        user: topobank.users.models.User
            User which should see the WorkflowResult.
        subject: Tag or Topography or Surface
            Instance which will be subject of the WorkflowResult.
        kwargs: dict
            Keyword arguments for the function which should be saved to database.

        Returns
        -------
        New WorkflowResult object.
        """
        _log.info(
            f"Submitting new WorkflowResult for user {user}, "
            f"subject {subject}, function {self}, kwargs: {kwargs}"
        )

        with transaction.atomic():
            # Create new entry in the WorkflowResult table and grant access to current user
            analysis = WorkflowResult.objects.create(
                subject_dispatch=WorkflowSubject.objects.create(subject),
                function=self,
                kwargs=kwargs,
                created_by=user,
                updated_by=user,
            )
            analysis.set_pending_state()
            analysis.permissions.grant_for_user(user, "edit")
            transaction.on_commit(
                partial(submit_analysis_task_to_celery, analysis, True)
            )
        return analysis

    def submit_again(self, analysis: WorkflowResult):
        """
        Submit WorkflowResult with same arguments and users.

        Parameters
        ----------
        analysis: WorkflowResult
            WorkflowResult instance to be renewed.

        Returns
        -------
        New WorkflowResult object.
        """
        _log.info(
            f"Renewing WorkflowResult {analysis.id}: Users "
            f"{[user for user, allow in analysis.permissions.get_users()]}, "
            f"function {self}, subject {analysis.subject}, kwargs: {analysis.kwargs}"
        )
        with transaction.atomic():
            analysis.set_pending_state()
            transaction.on_commit(
                partial(submit_analysis_task_to_celery, analysis, True)
            )
        return analysis


def resolve_workflow(identifier: str | int) -> Workflow:
    """Resolve workflow from URL, ID, or name."""
    errors = []

    # Try resolving as integer ID
    try:
        workflow_id = int(identifier)
        return Workflow.objects.get(pk=workflow_id)
    except ValueError:
        errors.append("not a valid integer ID")
    except Workflow.DoesNotExist:
        errors.append(f"no workflow found with ID {workflow_id}")

    # Try resolving as name
    try:
        return Workflow.objects.get(name=identifier)
    except Workflow.DoesNotExist:
        errors.append(f"no workflow found with name '{identifier}'")

    # Try resolving as URL
    try:
        match = resolve(urlparse(identifier).path)
        return Workflow.objects.get(**match.kwargs)
    except Resolver404:
        errors.append("invalid URL path")
    except Workflow.DoesNotExist:
        errors.append("URL resolved but no workflow found")
    except Exception as e:
        errors.append(f"URL resolution failed: {type(e).__name__}")

    raise ValueError(
        f"Could not resolve Workflow from '{identifier}'. "
        f"Attempted: ID, name, URL. Errors: {'; '.join(errors)}"
    )


class WorkflowTemplate(PermissionMixin, models.Model):
    """
    Workflow template stores a set of parameters for a workflow.
    """

    #
    # Manager
    #
    objects = AuthorizedManager()

    #
    # Permissions
    #
    permissions = models.ForeignKey(PermissionSet, on_delete=models.CASCADE, null=True)

    #
    # Name of stored parameters
    #
    name = models.CharField(max_length=255)

    #
    # Parameters to be passed to workflow
    #
    kwargs = models.JSONField(default=dict, blank=True)

    #
    # Workflow implementation
    #
    implementation = models.ForeignKey(
        Workflow, on_delete=models.CASCADE, null=True
    )

    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    def __str__(self):
        return (
            f"Workflow Template {self.id} - {self.name} for"
            f" implementation {self.implementation.display_name}"
        )

    def save(self, *args, **kwargs):
        created = self.pk is None
        if created and self.permissions is None:
            # Create a new permission set for this template
            _log.debug(
                f"Creating an empty permission set for template {self.id} which was "
                f"just created."
            )
            self.permissions = PermissionSet.objects.create()

        super().save(*args, **kwargs)
        if created:
            # Grant permissions to creator
            self.permissions.grant_for_user(self.creator, "full")
