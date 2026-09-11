"""
Models related to analyses.
"""

import json
import logging
from functools import partial
from typing import Union
from urllib.parse import urlparse

import pydantic
from django.conf import settings
from django.core.files.storage import default_storage
from django.db import models, transaction
from django.db.models import Q
from django.urls import resolve
from django.urls.exceptions import Resolver404

from topobank.authorization.models import EDIT, FULL

from ..authorization import get_permission_model
from ..authorization.mixins import PermissionMixin
from ..authorization.models import AuthorizedManager, ViewEditFull
from ..files.models import Manifest, ManifestSet
from ..manager.models import Surface, Tag, Topography
from ..supplib.dict import load_split_dict, store_split_dict
from ..taskapp.models import Configuration, TaskStateModel
from .registry import (
    WorkflowNotImplementedException,
    WorkflowNotRegisteredException,
    get_implementation,
)

_log = logging.getLogger(__name__)

RESULT_FILE_BASENAME = "result"


def cascade_or_set_null(collector, field, sub_objs, using):
    """Cascade delete unless the WorkflowResult has a name, in which case set null."""
    from django.db.models import CASCADE, SET_NULL

    named = [obj for obj in sub_objs if obj.name]
    unnamed = [obj for obj in sub_objs if not obj.name]
    if named:
        SET_NULL(collector, field, named, using)
    if unnamed:
        CASCADE(collector, field, unnamed, using)


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
    permissions = models.ForeignKey(
        getattr(settings, "TOPOBANK_PERMISSION_MODEL", "authorization.PermissionSet"),
        on_delete=models.CASCADE,
        null=True,
    )

    #
    # Workflow result parameters
    #

    # Name of the workflow (replaces the former ForeignKey to the Workflow DB model)
    workflow_name = models.CharField(max_length=255, null=True, db_index=True)

    # Definition of the subject
    subject_topography = models.ForeignKey(
        Topography,
        null=True,
        blank=True,
        on_delete=cascade_or_set_null,
        related_name="workflow_results",
    )
    subject_surface = models.ForeignKey(
        Surface,
        null=True,
        blank=True,
        on_delete=cascade_or_set_null,
        related_name="workflow_results",
    )
    subject_tag = models.ForeignKey(
        Tag,
        null=True,
        blank=True,
        on_delete=cascade_or_set_null,
        related_name="workflow_results",
    )

    # New surface set system (coexists with subject FKs)
    surfaces = models.ManyToManyField(
        Surface,
        blank=True,
        related_name="workflow_result_sets",
    )
    # Hash of subject IDs for quick lookup of existing results with the same subject set.
    # Prefixed with subject type, e.g. "surfaces:<sha256>".
    subject_hash = models.CharField(
        max_length=128, null=True, blank=True, db_index=True
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
    folder = models.ForeignKey(ManifestSet, on_delete=models.CASCADE, null=True)

    # Which workflow engine launched this result, and its handle to the run: a
    # serialised `topobank.analysis.engines.LaunchHandle`. None until launched,
    # and for results that predate engines (which were run by Celery).
    execution_handle = models.JSONField(null=True)

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
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    # Organization owning this WorkflowResult
    owned_by = models.ForeignKey(
        getattr(settings, "TOPOBANK_ORGANIZATION_MODEL", "organizations.Organization"),
        null=True,
        on_delete=models.CASCADE,
    )

    # Invalid is True if the subject was changed after the WorkflowResult was computed
    deprecation_time = models.DateTimeField(null=True)

    # If set, this result was soft-deleted. Stamped by container cascades (the
    # result rides along when the container it belongs to is soft-deleted) and
    # cleared again by a timestamp-matched restore. The custodian hard-deletes
    # stamped rows after TOPOBANK_DELETE_DELAY.
    deleted_at = models.DateTimeField(null=True)
    # User who soft-deleted this result. NULL when it is not deleted, when the
    # deletion was a system operation, or for results deleted before this
    # field existed. Only meaningful while `deleted_at` is set.
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        indexes = [
            # Index on task_start_time for ordering recent results
            models.Index(fields=["-task_start_time"], name="result_task_start_idx"),
            # Composite index for filtering by state and ordering by time
            # Used in: WHERE task_state = x ORDER BY task_start_time
            models.Index(
                fields=["task_state", "-task_start_time"], name="result_state_time_idx"
            ),
            # Composite index for filtering by workflow_name and ordering by time
            # Used in: WHERE workflow_name = x ORDER BY task_start_time
            models.Index(
                fields=["workflow_name", "-task_start_time"],
                name="result_workflow_time_idx",
            ),
            # Partial index for active (non-deprecated) results
            # Most common query pattern: active results ordered by time
            # Smaller than full index since it only includes non-deprecated rows
            models.Index(
                fields=["-task_start_time"],
                name="result_active_time_idx",
                condition=Q(deprecation_time__isnull=True),
            ),
            # Composite indexes for filtering by workflow_name + subject and ordering by time
            models.Index(
                fields=["workflow_name", "subject_topography", "-task_start_time"],
                name="result_func_topo_time_idx",
            ),
            models.Index(
                fields=["workflow_name", "subject_surface", "-task_start_time"],
                name="result_func_surf_time_idx",
            ),
            models.Index(
                fields=["workflow_name", "subject_tag", "-task_start_time"],
                name="result_func_tag_time_idx",
            ),
            # Serves the custodian's purge scan (deleted_at < cutoff) and the
            # cascade/restore sweeps that match rows by exact deleted_at.
            models.Index(fields=["deleted_at"], name="result_deleted_at_idx"),
        ]

    def __init__(self, *args, result=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._result = result  # temporary storage
        self._result_cache = result  # cached result
        self._result_metadata_cache = None  # cached toplevel result file

    def __str__(self):
        return f"WorkflowResult {self.id} on subject {self.subject} with state {self.task_state}"

    @property
    def function(self):
        """Return the Workflow for this result, or None if workflow_name is not set."""
        if self.workflow_name is None:
            return None
        return Workflow(name=self.workflow_name)

    def save(self, *args, **kwargs):
        """
        Save the WorkflowResult instance to the database.

        This method performs the following steps:
        1. Ensures permissions and folder are set, creating them if necessary.
        2. Calls the superclass's save method to persist the changes to the database and create
           the WorkflowResult instance if it is new.
        3. If a result dictionary was provided during initialization, it stores the result
           in the storage backend using the store_split_dict function and clears the
           temporary result storage.

        Note: When a result is given a name, its subject FKs are cleared so that
        named results are not tied to any specific subject and survive subject deletion.

        Parameters
        ----------
        *args : tuple
            Variable length argument list.
        **kwargs : dict
            Arbitrary keyword arguments.
        """

        # Named results are detached from their subject
        if self.name and (
            self.subject_topography_id is not None
            or self.subject_surface_id is not None
            or self.subject_tag_id is not None
        ):
            self.subject_topography = None
            self.subject_surface = None
            self.subject_tag = None
            if "update_fields" in kwargs and kwargs["update_fields"] is not None:
                kwargs["update_fields"] = list(kwargs["update_fields"]) + [
                    "subject_topography",
                    "subject_surface",
                    "subject_tag",
                ]

        # Ensure permissions and folder are set
        if self.permissions is None:
            _log.debug(
                "WorkflowResult has no permissions. Attempting to create new permission set."
            )
            if self.created_by:
                self.permissions = get_permission_model().objects.create()
                self.permissions.grant(self.created_by, FULL)
            else:
                raise RuntimeError(
                    "WorkflowResult is missing permission set and created_by. Cannot create permissions."
                )
        if self.folder is None:
            self.folder = ManifestSet.objects.create(
                permissions=self.permissions, read_only=True
            )
            if "update_fields" in kwargs:
                if kwargs["update_fields"] is not None:
                    kwargs["update_fields"].append("folder")

        if not self.pk:
            # New instance - ensure creator has EDIT permission
            if self.created_by:
                self.permissions.grant(self.created_by, EDIT)
            else:
                # This should be an error, but v1 does not enforce it like v2 does
                _log.warning("WorkflowResult saved without created_by user set.")

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
        Tag, Topography, Surface, or QuerySet
            The subject of the WorkflowResult. For surface-set analyses with a single
            surface, returns that Surface. For multi-surface sets, returns the queryset.
        """
        if self.subject_topography_id is not None:
            return self.subject_topography
        elif self.subject_surface_id is not None:
            return self.subject_surface
        elif self.subject_tag_id is not None:
            return self.subject_tag
        # Fall back to surfaces M2M for surface-set analyses
        surfaces = self.surfaces.all()
        if surfaces.exists():
            if surfaces.count() == 1:
                return surfaces.first()
            return surfaces
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
            try:
                self._result_cache = load_split_dict(
                    self.folder, RESULT_FILE_BASENAME
                )
            except FileNotFoundError:
                # Artifact-only workflows (e.g. the v3 map tasks) return None
                # from their implementation, so no result.json is stored —
                # honor the documented "None if there is nothing yet" contract
                # instead of leaking the storage lookup failure.
                return None
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
        self.folder = ManifestSet.objects.create(
            permissions=self.permissions, read_only=True
        )
        self.save(update_fields=["folder"])
        dir_tuple = default_storage.listdir(self.storage_prefix)
        for filename in dir_tuple[1]:
            manifest = Manifest.objects.create(
                permissions=self.permissions,
                filename=filename,
                kind="der",
                folder=self.folder,
            )
            manifest.file.name = f"{self.storage_prefix}/{filename}"
            manifest.save(update_fields=["file"])

    def get_related_surfaces(self):
        """Returns sequence of surface instances related to the subject of this WorkflowResult."""
        return self.subject.get_related_surfaces()

    @property
    def implementation(self):
        return Workflow(name=self.workflow_name).implementation

    def get_celery_queue(self) -> str:
        """
        Deprecated: the broker queue the Celery workflow engine dispatches this
        result to. Queue selection is the Celery engine's business.
        """
        from .celery.engine import CeleryWorkflowEngine

        return CeleryWorkflowEngine().queue_for(self)

    # --- Workflow engine -------------------------------------------------
    #
    # A result is run by exactly one workflow engine (see
    # `topobank.analysis.engines`). Everything below asks that engine; the
    # reconciliation in `get_task_state` (inherited) is unchanged and merely
    # sees the engine's answer where it used to see Celery's.

    def get_workflow_engine(self):
        """The workflow engine responsible for this result's run."""
        from .engines import engine_for_result

        return engine_for_result(self)

    def set_pending_state(self, autosave=True):
        # A new launch produces a new handle
        super().set_pending_state(autosave=False)
        self.execution_handle = None
        if autosave:
            self.save(update_fields=[*self.PENDING_STATE_FIELDS, "execution_handle"])

    def poll(self):
        """Ask the workflow engine what it knows about this result's run."""
        if not hasattr(self, "_cached_run_info"):
            self._cached_run_info = self.get_workflow_engine().poll(self)
        return self._cached_run_info

    def get_celery_state(self):
        """Return the state of the run as reported by the workflow engine"""
        # Optimization: a terminal state is trusted without asking the engine
        if self.task_state in (self.SUCCESS, self.FAILURE):
            return self.task_state
        return self.poll().state

    def get_task_progress(self):
        """Return progress of the run, if running"""
        if self.task_state == self.SUCCESS:
            return 100.0
        elif self.task_state == self.FAILURE:
            return None
        return self.poll().progress

    def get_task_messages(self):
        """Return progress message(s) of the run, if running"""
        if self.task_state in (self.SUCCESS, self.FAILURE):
            return []
        return self.poll().messages

    def get_task_error(self):
        """Return a string representation of any error occurred during the run"""
        # Return self-reported task error, if any
        if self.task_error:
            return self.task_error

        # If there is none, ask the engine
        error = self.poll().error
        if error:
            from .status import StatusReport, apply_status_report

            # The engine holds an error the run did not report itself; keep it
            apply_status_report(self, StatusReport(state=self.FAILURE, error=error))
            return self.task_error
        return None

    def cancel_task(self):
        """Cancel the run, if running"""
        self.get_workflow_engine().cancel(self)

    # FIXME: discuss whether to remove this method and use the generic one from PermissionMixin
    # overrides PermissionMixin.authorize_user <- this one returns nothing, raises exception on failure
    # v This one grants the user permission to access the WorkflowResult without permission.
    def authorize_user(
        self, user: settings.AUTH_USER_MODEL, access_level: ViewEditFull = "view"
    ):
        """
        Returns an exception if given user should not be able to see this WorkflowResult.
        """
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
        return self.subject_topography_id is not None

    @property
    def is_surface_related(self) -> bool:
        """Returns True, if the WorkflowResult subject is a surface, else False."""
        return self.subject_surface_id is not None

    @property
    def is_tag_related(self) -> bool:
        """Returns True, if the WorkflowResult subject is a tag, else False."""
        return self.subject_tag_id is not None

    @staticmethod
    def Q(subject) -> models.Q:
        """Build a Q object to filter WorkflowResults for a single subject."""
        if isinstance(subject, Tag):
            return models.Q(subject_tag_id=subject.id)
        elif isinstance(subject, Topography):
            return models.Q(subject_topography_id=subject.id)
        elif isinstance(subject, Surface):
            return models.Q(subject_surface_id=subject.id)
        else:
            raise ValueError(
                "`subject` argument must be of type `Tag`, `Topography` or `Surface`, "
                f"not {type(subject)}."
            )

    @staticmethod
    def Qs(user, subjects) -> models.Q | None:
        """Build a Q object to filter WorkflowResults for multiple subjects."""
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
        if tag_ids:
            q = models.Q(subject_tag_id__in=tag_ids) & Q(
                permissions__user_permissions__user=user
            )
            query = q
        if topography_ids:
            q = models.Q(subject_topography_id__in=topography_ids)
            query = query | q if query else q
        if surface_ids:
            q = models.Q(subject_surface_id__in=surface_ids)
            query = query | q if query else q
        return query

    @staticmethod
    def compute_subject_hash(subject_type, subject_ids):
        """Compute a deterministic hash for a set of subject IDs, prefixed by type."""
        from .workflows import compute_subject_hash

        return compute_subject_hash(subject_type, subject_ids)

    def update_subject_hash(self):
        """Recompute and save subject_hash from current subject fields."""
        ids = list(self.surfaces.values_list("id", flat=True))
        if ids:
            self.subject_hash = self.compute_subject_hash("surfaces", ids)
        elif self.subject_topography_id is not None:
            self.subject_hash = self.compute_subject_hash("topography", [self.subject_topography_id])
        elif self.subject_surface_id is not None:
            self.subject_hash = self.compute_subject_hash("surface", [self.subject_surface_id])
        elif self.subject_tag_id is not None:
            self.subject_hash = self.compute_subject_hash("tag", [self.subject_tag_id])
        else:
            self.subject_hash = None
        self.save(update_fields=["subject_hash"])

    def submit(self, force_submit: bool = False) -> "WorkflowResult":
        with transaction.atomic():
            self.set_pending_state()
            transaction.on_commit(
                partial(submit_workflow, self, force_submit)
            )
        return self

    def submit_again(self, force_submit: bool = True) -> "WorkflowResult":
        return self.submit(force_submit=force_submit)

    # v1 only
    def set_name(self, name: str, description: str = None):
        """
        DEPRECATED: v1 use only. Name is now set via normal field update and save.
        Setting a name essentially saves the WorkflowResult, i.e. it is no longer deleted
        when the WorkflowResult subject is deleted.
        """
        self.name = name
        self.description = description
        self.subject_topography = None
        self.subject_surface = None
        self.subject_tag = None
        self.save(
            update_fields=[
                "name",
                "description",
                "subject_topography",
                "subject_surface",
                "subject_tag",
            ]
        )


def submit_workflow(analysis: WorkflowResult, force_submit: bool):
    """
    Hand a WorkflowResult to the workflow engine that runs its workflow.

    This is the single point where analysis work leaves topobank. It is
    typically run in an on_commit hook so that the row is visible to whatever
    worker the engine starts. Note: on_commit will not execute in tests, unless
    transaction=True is added to pytest.mark.django_db.
    """
    from .engines import resolve_workflow
    from .status import StatusReport, apply_status_report

    # TODO: force_submit is currently hardcoded to True everywhere this is called.
    resolved = resolve_workflow(analysis.workflow_name)
    if resolved is None:
        # Nothing can run this; an exception here would vanish in the on_commit
        # hook, so record the failure where the user will see it.
        _log.error(
            "WorkflowResult %s names workflow %r, which no workflow engine knows.",
            analysis.id,
            analysis.workflow_name,
        )
        apply_status_report(
            analysis,
            StatusReport(
                state=WorkflowResult.FAILURE,
                error=f"No workflow engine can run workflow '{analysis.workflow_name}'.",
            ),
        )
        return

    engine, _ = resolved
    _log.debug(
        "Launching WorkflowResult %s on workflow engine %r...", analysis.id, engine.name
    )
    handle = engine.launch(analysis, force=force_submit)
    analysis.execution_handle = handle.model_dump()
    analysis.save(update_fields=["execution_handle"])


# Historical name, kept for callers outside this repository.
submit_analysis_task_to_celery = submit_workflow


class Workflow:
    """
    A workflow, by name.

    This is a plain value object, not a Django model; there is no table of
    workflows. It resolves its name to the descriptor (shim) a workflow engine
    registered under it and answers the questions the API asks about a
    workflow - display name, parameter schema and defaults, outputs, accepted
    subjects - by delegating to that descriptor. It is also where a result is
    asked for: `submit`, `submit_for_surfaces` and `submit_again` apply the
    business rules and hand the result to its engine.

    Running a workflow is the engine's business and is not on this class; see
    :mod:`topobank.analysis.celery.workflows` for how the Celery engine does it.
    """

    def __init__(self, name: str):
        self.name = name

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"Workflow({self.name!r})"

    def __eq__(self, other):
        if isinstance(other, Workflow):
            return self.name == other.name
        return NotImplemented

    def __hash__(self):
        return hash(self.name)

    # --- Resolution ------------------------------------------------------

    @property
    def implementation(self):
        """
        The descriptor (shim) class registered for this workflow, or None if
        no workflow engine knows the name.

        Resolved over the configured engines in priority order; the class is
        the engine's own shim, so it also knows how to run the workflow there.
        """
        return get_implementation(name=self.name)

    @property
    def descriptor(self):
        """
        The descriptor (shim) class registered for this workflow.

        Raises
        ------
        WorkflowNotRegisteredException
            If no workflow engine knows the name.
        """
        descriptor = self.implementation
        if descriptor is None:
            raise WorkflowNotRegisteredException(self.name)
        return descriptor

    @property
    def is_registered(self) -> bool:
        """Whether some workflow engine knows this workflow."""
        return self.implementation is not None

    # --- Metadata, delegated to the descriptor ---------------------------

    @property
    def display_name(self) -> str:
        """
        The workflow's display name.

        Falls back to the name itself for a workflow no engine knows: results
        outlive the workflows that produced them and still need a label.
        """
        descriptor = self.implementation
        return self.name if descriptor is None else descriptor.Meta.display_name

    def has_implementation(self, model_class) -> bool:
        """Whether the workflow accepts subjects of `model_class`; False if unknown."""
        descriptor = self.implementation
        return descriptor is not None and descriptor.has_implementation(model_class)

    def get_default_kwargs(self) -> dict:
        """
        The default parameters as a dictionary.

        Empty for a workflow whose parameters have required fields, which has
        no complete set of defaults.
        """
        try:
            return self.descriptor.get_default_kwargs()
        except pydantic.ValidationError:
            return {}

    def get_kwargs_schema(self) -> dict:
        """JSON schema of the parameters."""
        return self.descriptor.get_kwargs_schema()

    def get_outputs_schema(self) -> list:
        """The declared output files, each with its schema."""
        return self.descriptor.get_outputs_schema()

    def clean_kwargs(self, kwargs: Union[dict, None], fill_missing: bool = True) -> dict:
        """
        Validate parameters against the workflow's `Parameters` model.

        Parameters
        ----------
        kwargs : dict or None
            Parameters as given; None stands for "all defaults".
        fill_missing : bool, optional
            Fill in defaults for parameters not given. (Default: True)

        Raises
        ------
        pydantic.ValidationError
            If the parameters do not validate.
        WorkflowNotRegisteredException
            If no workflow engine knows the workflow.
        """
        return self.descriptor.clean_kwargs(kwargs, fill_missing=fill_missing)

    # --- Asking for results ----------------------------------------------

    def submit(
        self,
        user: settings.AUTH_USER_MODEL,
        subject: Union[Tag, Surface, Topography],
        kwargs: dict = None,
        force_submit: bool = False,
    ) -> WorkflowResult:
        """
        Ask for this workflow's result on `subject`, running it if needed.

        A result that is pending, running or finished successfully for the
        same subject and parameters, and that `user` may see, is returned as
        is. Otherwise failed leftovers are removed and a new result is created
        and handed to the workflow engine once the transaction commits.

        Parameters
        ----------
        user : topobank.users.models.User
            User asking; must be allowed to view `subject`, gets `edit` on a
            new result.
        subject : Tag or Topography or Surface
            Subject of the result.
        kwargs : dict, optional
            Parameters. Missing ones are filled with the workflow's defaults;
            None means all defaults. (Default: None)
        force_submit : bool, optional
            Create and run a new result even if a viable one exists.
            (Default: False)

        Raises
        ------
        WorkflowNotImplementedException
            If the workflow does not accept subjects of this type, or no
            engine knows the workflow.
        """
        from .store import Reuse, find_or_create
        from .workflows import ResultRequest

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

        request = ResultRequest(workflow_name=self.name, subject=subject, kwargs=kwargs)
        with transaction.atomic():
            found = find_or_create(
                request, user=user, reuse=Reuse.VIABLE, force=force_submit, for_user=True
            )
            if found.needs_run:
                transaction.on_commit(partial(submit_workflow, found.result, True))
        return found.result

    def submit_for_surfaces(
        self,
        user: settings.AUTH_USER_MODEL,
        surfaces: list,
        kwargs: dict = None,
        owned_by_id=None,
        force_submit: bool = False,
        ignore_existing: bool = False,
    ) -> WorkflowResult:
        """
        Ask for this workflow's result on a set of surfaces, running it if needed.

        Reuse follows the same rule as `submit`, except that any viable result
        for the same surface set and parameters counts, not only those `user`
        may see.

        Parameters
        ----------
        user : User
            User asking; gets `edit` on a new result.
        surfaces : list[Surface]
            The surfaces making up the surface set.
        kwargs : dict, optional
            Parameters. (Default: None)
        owned_by_id : int, optional
            Owner of a new result; defaults to the owner of the first surface.
        force_submit : bool, optional
            Create and run a new result even if a viable one exists.
            (Default: False)
        ignore_existing : bool, optional
            Always create a new result, without looking at or deleting any
            existing one. (Default: False)
        """
        from .store import Reuse, find_or_create
        from .workflows import ResultRequest

        # Permission checks (commented out during initial implementation)
        # for surface in surfaces:
        #     surface.authorize_user(user, "view")

        request = ResultRequest(workflow_name=self.name, surfaces=surfaces, kwargs=kwargs)
        with transaction.atomic():
            found = find_or_create(
                request,
                user=user,
                reuse=Reuse.NEVER if ignore_existing else Reuse.VIABLE,
                force=force_submit,
                owned_by_id=owned_by_id,
            )
            if found.needs_run:
                transaction.on_commit(partial(submit_workflow, found.result, True))
        return found.result

    def submit_again(self, analysis: WorkflowResult) -> WorkflowResult:
        """
        Run an existing result again, with the same subject, parameters and users.

        Parameters
        ----------
        analysis : WorkflowResult
            The result to run again.
        """
        _log.info(
            f"Renewing WorkflowResult {analysis.id}: Users "
            f"{[user for user, allow in analysis.permissions.get_users()]}, "
            f"function {self}, subject {analysis.subject}, kwargs: {analysis.kwargs}"
        )
        with transaction.atomic():
            analysis.set_pending_state()
            transaction.on_commit(partial(submit_workflow, analysis, True))
        return analysis


def resolve_workflow(identifier: str | int) -> Workflow:
    """Resolve workflow from name or URL.

    Accepts a plain workflow name string (e.g. 'topobank.testing.test') or a
    URL pointing to the workflow detail endpoint.  Integer IDs are no longer
    supported — workflows have no database primary key.
    """
    # Try as a plain name string
    if isinstance(identifier, str):
        if get_implementation(name=identifier) is not None:
            return Workflow(name=identifier)

        # Try resolving as a URL
        try:
            match = resolve(urlparse(identifier).path)
            name = match.kwargs.get("name")
            if name and get_implementation(name=name) is not None:
                return Workflow(name=name)
        except (Resolver404, Exception):
            pass

    raise ValueError(
        f"Could not resolve Workflow from '{identifier}'. "
        f"No workflow with that name or URL found in registry."
    )
