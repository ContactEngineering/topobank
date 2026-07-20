import traceback
import tracemalloc
from typing import Any, Dict

import celery
from celery.utils.log import get_task_logger
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from muTimer import Timer
from SurfaceTopography.Support import doi

from ..manager.models import Surface, Tag, Topography
from ..supplib.dict import store_split_dict
from ..taskapp.celeryapp import app
from ..taskapp.models import Configuration
from ..taskapp.tasks import ProgressRecorder
from ..taskapp.utils import get_package_version
from .workflows import WorkflowDefinition

_log = get_task_logger(__name__)


def get_current_configuration():
    """
    Determine current configuration (package versions) and create appropriate
    database entries.

    The configuration is needed in order to track down analysis results to specific
    module and package versions. Like this it is possible to find all analyses which
    have been calculated with buggy packages.

    :return: Configuration instance which can be used for analyses
    """
    versions = [
        get_package_version(pkg_name, version_expr)
        for pkg_name, version_expr, license, homepage in settings.TRACKED_DEPENDENCIES
    ]

    def make_config_from_versions():
        c = Configuration.objects.create()
        c.versions.set(versions)
        return c

    if Configuration.objects.count() == 0:
        return make_config_from_versions()

    #
    # Find out whether the latest configuration has exactly these versions
    #
    latest_config = Configuration.objects.latest("valid_since")

    current_version_ids = set(v.id for v in versions)
    latest_version_ids = set(v.id for v in latest_config.versions.all())

    if current_version_ids == latest_version_ids:
        return latest_config
    else:
        return make_config_from_versions()


@app.task(bind=True, soft_time_limit=3600, time_limit=3700)
def schedule_workflow(
    self: celery.Task,
    analysis_id: int,
    force: bool,
    is_dependency: bool = False,
    parent_id: int = None,
):
    """Schedule a workflow, checking and setting up dependencies first.

    This task handles the dependency resolution phase:
    1. Loads the analysis from database
    2. Checks if dependencies exist and their states
    3. If dependencies need scheduling: creates chord with execute_workflow as callback
    4. If no dependencies or all complete: directly calls execute_workflow

    Parameters
    ----------
    self : celery.app.task.Task
        Celery task on execution (because of bind=True).
    analysis_id : int
        ID of `topobank.analysis.WorkflowResult` instance.
    force : bool
        Submission was forced, which means we need to renew dependencies.
    is_dependency : bool, optional
        Whether this workflow was scheduled as a dependency of another
        workflow. (Default: False)
    parent_id : int, optional
        ID of the WorkflowResult whose scheduling triggered this run, when
        this workflow runs as a dependency. Attribution travels with the
        Celery task rather than the (shared) WorkflowResult row, so
        concurrent parents re-running the same dependency each carry their
        own id. (Default: None)
    """
    from .models import WorkflowResult

    #
    # Get analysis instance from database
    #
    try:
        celery_queue = self.request.delivery_info["routing_key"]
    except TypeError:
        celery_queue = None

    # Optimize query with select_related to reduce DB round trips
    analysis = (
        WorkflowResult.objects.select_related(
            "subject_topography",
            "subject_surface",
            "subject_tag",
            "configuration",
            "created_by",
            "owned_by",
        )
        .prefetch_related("permissions", "surfaces")
        .get(id=analysis_id)
    )
    _log.info(
        f"{analysis_id}/{self.request.id}: Scheduling workflow -- "
        f"Queue: {celery_queue}, force recalculation: {force} -- "
        f"Workflow: '{analysis.workflow_name}', subject: '{analysis.subject}', "
        f"kwargs: {analysis.kwargs}, task_state: '{analysis.task_state}'"
    )

    #
    # Check state - don't reschedule completed/failed tasks
    #
    if (
        analysis.task_state in [WorkflowResult.FAILURE, WorkflowResult.SUCCESS]
        and not force
    ):
        s = (
            "completed successfully"
            if analysis.task_state == WorkflowResult.SUCCESS
            else "failed"
        )
        _log.debug(
            f"{self.request.id}: Terminating schedule_workflow because this analysis has "
            f"{s} in a previous run."
        )
        return

    #
    # Update entry to indicate we started scheduling
    #
    analysis.task_id = self.request.id
    analysis.task_start_time = timezone.now()
    analysis.configuration = get_current_configuration()

    #
    # Check and run dependencies
    #
    dependencies = analysis.function.get_dependencies(analysis)  # This is a dict!

    if len(dependencies) > 0:
        _log.debug(f"{self.request.id}: Checking analysis dependencies...")
        finished_dependencies, scheduled_dependencies = prepare_dependency_tasks(
            dependencies, force, analysis.created_by, analysis
        )

        if len(scheduled_dependencies) > 0:
            # Dependencies need to be scheduled first
            for dep in scheduled_dependencies.values():
                dep.set_pending_state()

            # Store all dependencies (both finished and scheduled)
            all_deps = {**finished_dependencies, **scheduled_dependencies}
            analysis.dependencies = {key: dep.id for key, dep in all_deps.items()}

            # Set state to PENDING_DEPENDENCIES - we're waiting for deps to complete
            analysis.task_state = WorkflowResult.PENDING_DEPENDENCIES
            analysis.launcher_task_id = self.request.id
            analysis.save()

            # Create chord: run all dependencies, then execute this workflow
            task = celery.chord(
                (
                    schedule_workflow.si(
                        dep.id, False, is_dependency=True, parent_id=analysis.id
                    ).set(queue=celery_queue)
                    for dep in scheduled_dependencies.values()
                ),
                execute_workflow.si(
                    analysis.id, is_dependency=is_dependency, parent_id=parent_id
                ).set(queue=celery_queue),
            ).apply_async()

            # Store chord task id
            analysis.task_id = task.id
            analysis.save(update_fields=["task_id"])

            _log.debug(
                f"{analysis_id}/{self.request.id}: Submitted "
                f"{len(scheduled_dependencies)} dependencies; waiting for resolution."
            )
            return

        # All dependencies are already finished
        analysis.dependencies = {
            key: dep.id for key, dep in finished_dependencies.items()
        }
        analysis.save()

        # Check if any dependency failed
        if any(
            dep.task_state != WorkflowResult.SUCCESS
            for dep in finished_dependencies.values()
        ):
            analysis.task_state = WorkflowResult.FAILURE
            analysis.task_error = "A dependent analysis failed."
            analysis.save()
            _log.debug(f"{analysis_id}/{self.request.id}: A dependency failed.")
            return

    else:
        _log.debug(f"{analysis_id}/{self.request.id}: Analysis has no dependencies.")
        analysis.dependencies = {}
        analysis.save()

    # No dependencies or all dependencies finished successfully - execute directly.
    # Use .apply() (synchronous) so that when schedule_workflow is used as a chord
    # header task, the chord does not fire its callback until the actual work is done.
    # Using .apply_async() here would cause a race condition: the chord would see
    # schedule_workflow as "complete" while execute_workflow is still running.
    _log.debug(f"{analysis_id}/{self.request.id}: Calling execute_workflow directly.")
    execute_workflow.apply(
        args=(analysis.id, is_dependency), kwargs={"parent_id": parent_id}
    )


def _fail_parent_on_dependency_failure(parent_id, dependency, request_id):
    """Mark a parent workflow FAILURE because one of its dependencies failed.

    Called from the dependency's ``execute_workflow`` when it errors, so the
    parent does not hang in PENDING_DEPENDENCIES waiting for a chord callback
    that will never fire (a failed chord header suppresses the callback).

    Uses a filtered ``update()`` so it is atomic and never clobbers a parent
    that has already reached a terminal state (or was reset/rerun): only rows
    still waiting are transitioned. The dependency's error/traceback are copied
    onto the parent so the UI shows why it failed.
    """
    from .models import WorkflowResult

    waiting_states = [
        WorkflowResult.NOTRUN,
        WorkflowResult.PENDING,
        WorkflowResult.RETRY,
        WorkflowResult.STARTED,
        WorkflowResult.PENDING_DEPENDENCIES,
    ]
    updated = WorkflowResult.objects.filter(
        id=parent_id, task_state__in=waiting_states
    ).update(
        task_state=WorkflowResult.FAILURE,
        task_error=dependency.task_error or "A dependent analysis failed.",
        task_traceback=dependency.task_traceback,
        task_end_time=timezone.now(),
    )
    if updated:
        _log.warning(
            "%s: dependency %s failed; propagated FAILURE to parent %s.",
            request_id,
            dependency.id,
            parent_id,
        )


@app.task(bind=True, soft_time_limit=3600, time_limit=3700)
def execute_workflow(
    self: celery.Task,
    analysis_id: int,
    is_dependency: bool = False,
    parent_id: int = None,
):
    """Execute the actual workflow after dependencies are resolved.

    This task assumes all dependencies are already complete and handles:
    1. Loading finished dependencies
    2. Running the actual workflow via analysis.eval_self()
    3. Storing results and statistics

    Parameters
    ----------
    self : celery.app.task.Task
        Celery task on execution (because of bind=True).
    analysis_id : int
        ID of `topobank.analysis.WorkflowResult` instance.
    is_dependency : bool, optional
        Whether this workflow runs as a dependency of another workflow.
        (Default: False)
    parent_id : int, optional
        ID of the WorkflowResult whose scheduling triggered this run, when
        running as a dependency. (Default: None)
    """
    from .models import RESULT_FILE_BASENAME, WorkflowResult

    #
    # Get analysis instance from database
    #
    analysis = (
        WorkflowResult.objects.select_related(
            "subject_topography",
            "subject_surface",
            "subject_tag",
            "configuration",
            "created_by",
            "owned_by",
        )
        .prefetch_related("permissions", "surfaces")
        .get(id=analysis_id)
    )

    _log.info(
        f"{analysis_id}/{self.request.id}: Executing workflow -- "
        f"Workflow: '{analysis.workflow_name}', subject: '{analysis.subject}', "
        f"kwargs: {analysis.kwargs}"
    )

    #
    # Check state - don't re-execute completed/failed tasks
    #
    if analysis.task_state in [WorkflowResult.FAILURE, WorkflowResult.SUCCESS]:
        s = (
            "completed successfully"
            if analysis.task_state == WorkflowResult.SUCCESS
            else "failed"
        )
        _log.debug(
            f"{self.request.id}: Terminating execute_workflow because this analysis has "
            f"{s} in a previous run."
        )
        return

    #
    # Update state to STARTED - we're now actually running the workflow
    #
    analysis.task_state = WorkflowResult.STARTED
    analysis.task_id = self.request.id
    # Only set start time if not already set (e.g., from schedule_workflow)
    if analysis.task_start_time is None:
        analysis.task_start_time = timezone.now()
    analysis.configuration = get_current_configuration()
    analysis.save()

    #
    # Load finished dependencies
    #
    finished_dependencies = {}
    if analysis.dependencies:
        for key, dep_id in analysis.dependencies.items():
            # Convert JSON string key back to integer if it represents an integer.
            # JSON only supports string keys, so integer keys (e.g., surface.id)
            # get serialized as strings. We need to convert them back for workflow
            # implementations that use integer keys to access dependencies.
            try:
                key = int(key)
            except ValueError:
                pass  # Keep as string if not a valid integer
            dep = WorkflowResult.objects.get(id=dep_id)
            if dep.task_state != WorkflowResult.SUCCESS:
                # A dependency failed - we cannot proceed
                # Copy error and traceback from the failed dependency
                error_msg = dep.task_error or f"Dependency '{key}' failed."
                analysis.task_state = WorkflowResult.FAILURE
                analysis.task_error = error_msg
                analysis.task_traceback = dep.task_traceback
                analysis.task_end_time = timezone.now()
                analysis.save()
                _log.warning(
                    "%s/%s: Dependency '%s' (id=%s) is in state '%s', cannot execute workflow.",
                    analysis_id,
                    self.request.id,
                    key,
                    dep_id,
                    dep.task_state,
                )
                # Raise so Celery reports task_failure (not task_success)
                raise RuntimeError(error_msg)
            finished_dependencies[key] = dep

    def save_result(result, task_state, peak_memory=None, dois=set(), timer=None):
        analysis.task_state = task_state
        # Only store result if the implementation returned one
        if result is not None:
            store_split_dict(analysis.folder, RESULT_FILE_BASENAME, result)
        analysis.task_memory = peak_memory
        analysis.dois = list(dois)
        if timer is not None:
            analysis.task_timer = timer.to_dict()
        analysis.save()

        if peak_memory is not None:
            _log.debug(
                f"{analysis_id}/{self.request.id}: Task state: '{task_state}', "
                f"duration: {analysis.task_duration}, "
                f"peak memory usage: {int(peak_memory / 1024 / 1024)} MB"
            )
        else:
            _log.debug(
                f"{analysis_id}/{self.request.id}: Task state: '{task_state}', "
                f"duration: {analysis.task_duration}"
            )

    @doi()
    def evaluate_function(progress_recorder, timer, finished_analyses):
        if len(finished_analyses) > 0:
            return analysis.eval_self(
                dependencies=finished_analyses,
                progress_recorder=progress_recorder,
                timer=timer,
            )
        else:
            return analysis.eval_self(
                progress_recorder=progress_recorder,
                timer=timer,
            )

    #
    # Actually perform the workflow
    #
    _log.debug(
        f"{analysis_id}/{self.request.id}: Starting evaluation of analysis function..."
    )
    try:
        dois = set()
        tracemalloc.start()
        tracemalloc.reset_peak()
        timer = Timer(str(self.request.id))
        on_progress = None
        # If a callback is configured, create a progress callback.
        callback_path = getattr(settings, "WORKFLOW_PROGRESS_CALLBACK", None)
        if callback_path:
            from django.utils.module_loading import import_string

            task_type = "dependency" if is_dependency else "analysis"
            on_progress = import_string(callback_path)(
                str(self.request.id),
                org_id=getattr(analysis, "owned_by_id", None),
                task_info={
                    "type": task_type,
                    "name": (
                        analysis.function.display_name
                        if analysis.function
                        else "Workflow"
                    ),
                    "workflow_result_id": analysis.id,
                    "organization_id": getattr(analysis, "owned_by_id", None),
                    "parent_workflow_result_id": parent_id,
                },
            )

        result = evaluate_function(
            dois=dois,
            progress_recorder=ProgressRecorder(self, on_progress=on_progress),
            timer=timer,
            finished_analyses=finished_dependencies,
        )
        size, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        save_result(
            result, WorkflowResult.SUCCESS, peak_memory=peak, dois=dois, timer=timer
        )
    except Exception as exc:
        _log.exception(
            f"{analysis_id}/{self.request.id}: Exception during evaluation: {exc}"
        )
        analysis.task_state = WorkflowResult.FAILURE
        analysis.task_traceback = traceback.format_exc().replace("\x00", "")
        analysis.task_error = str(exc).replace("\x00", "")
        analysis.save()
        # Propagate the failure to the parent when this ran as a dependency.
        #
        # The parent waits for its dependencies via a Celery chord whose callback
        # is the parent's own execute_workflow. But a failed chord *header* means
        # Celery never fires that callback, so the parent would be stranded in
        # PENDING_DEPENDENCIES until it is declared lost (28800 s) — surfacing in
        # the UI as an indefinite "Queued". Failing the parent here, at the point
        # the dependency actually fails, is deterministic and does not depend on
        # the chord callback ever running. (If the callback does run later, it
        # early-returns on seeing the parent already in a terminal state.)
        if is_dependency and parent_id is not None:
            _fail_parent_on_dependency_failure(parent_id, analysis, self.request.id)
        raise
    finally:
        try:
            analysis = WorkflowResult.objects.get(id=analysis_id)
        except WorkflowResult.DoesNotExist:
            _log.debug(
                f"{analysis_id}/{self.request.id}: Analysis {analysis_id} does not exist."
            )
            pass
        else:
            analysis.task_end_time = timezone.now()
            analysis.save(update_fields=["task_end_time"])
    _log.debug(f"{analysis_id}/{self.request.id}: Workflow finished normally.")


# Keep perform_analysis as an alias for backward compatibility
@app.task(bind=True, soft_time_limit=3600, time_limit=3700)
def perform_analysis(self: celery.Task, analysis_id: int, force: bool):
    """Perform an analysis which is already present in the database.

    This is a backward-compatible wrapper that calls schedule_workflow.

    Parameters
    ----------
    self : celery.app.task.Task
        Celery task on execution (because of bind=True).
    analysis_id : int
        ID of `topobank.analysis.WorkflowResult` instance.
    force : bool
        Submission was forced, which means we need to renew dependencies.
    """
    # Delegate to schedule_workflow
    return schedule_workflow.apply(args=(analysis_id, force))


def current_statistics(user=None):
    """Return some statistics about managed data.

    These values are calculated from current counts
    of database objects.

    Parameters
    ----------
        user: User instance
            If given, the statistics is only related to the surfaces of a given user
            (as created_by)

    Returns
    -------
        dict with keys

        - num_surfaces_excluding_publications
        - num_topographies_excluding_publications
        - num_analyses_excluding_publications
    """
    from .models import WorkflowResult

    if hasattr(Surface, "publication"):
        if user:
            unpublished_surfaces = Surface.objects.filter(
                created_by=user, publication__isnull=True
            )
        else:
            unpublished_surfaces = Surface.objects.filter(publication__isnull=True)
    else:
        if user:
            unpublished_surfaces = Surface.objects.filter(created_by=user)
        else:
            unpublished_surfaces = Surface.objects.all()
    unpublished_topographies = Topography.objects.filter(
        surface__in=unpublished_surfaces
    )
    unpublished_analyses = WorkflowResult.objects.filter(
        subject_topography__in=unpublished_topographies
    )

    return dict(
        num_surfaces_excluding_publications=unpublished_surfaces.count(),
        num_topographies_excluding_publications=unpublished_topographies.count(),
        num_analyses_excluding_publications=unpublished_analyses.count(),
    )


def prepare_dependency_tasks(
    dependencies: Dict[Any, WorkflowDefinition], force: bool, user=None, parent=None
):
    from .models import WorkflowResult

    # Determine if parent uses the surface set (M2M) path
    use_surfaces_path = parent is not None and parent.surfaces.exists()

    finished_dependent_analyses = {}  # Everything that finished or failed
    scheduled_dependent_analyses = {}  # Everything that needs to be scheduled
    for key, dependency in dependencies.items():
        if key in scheduled_dependent_analyses or key in finished_dependent_analyses:
            raise RuntimeError(f"Dependency '{key}' already dependent or finished.")

        # Get analysis function
        function = dependency.function

        # Clean kwargs for dependency (fill potentially missing values)
        kwargs = function.clean_kwargs(dependency.kwargs)

        # Compute subject_hash for this dependency
        subject = dependency.subject
        if use_surfaces_path and isinstance(subject, Surface):
            subject_hash = WorkflowResult.compute_subject_hash("surfaces", [subject.id])
        elif isinstance(subject, Surface):
            subject_hash = WorkflowResult.compute_subject_hash("surface", [subject.id])
        elif isinstance(subject, Topography):
            subject_hash = WorkflowResult.compute_subject_hash(
                "topography", [subject.id]
            )
        elif isinstance(subject, Tag):
            subject_hash = WorkflowResult.compute_subject_hash("tag", [subject.id])
        else:
            raise ValueError(f"Unsupported dependency subject type: {type(subject)}")

        existing_analysis_qs = WorkflowResult.objects.filter(
            workflow_name=dependency.function.name,
            subject_hash=subject_hash,
            kwargs=kwargs,
        ).select_related("subject_topography", "subject_surface", "subject_tag")
        if use_surfaces_path and isinstance(subject, Surface):
            existing_analysis_qs = existing_analysis_qs.prefetch_related("surfaces")
        existing_analysis = existing_analysis_qs.order_by("-task_start_time").first()

        if existing_analysis is None:
            with transaction.atomic():
                create_kwargs = dict(
                    permissions=parent.permissions,
                    workflow_name=function.name,
                    task_state=WorkflowResult.PENDING,
                    kwargs=kwargs,
                    created_by=user,
                    owned_by=parent.owned_by,
                    metadata={"parent_workflow_result_id": parent.id},
                    subject_hash=subject_hash,
                )
                if use_surfaces_path and isinstance(subject, Surface):
                    pass  # subject stored in M2M below; no FK field set
                elif isinstance(subject, Surface):
                    create_kwargs["subject_surface"] = subject
                elif isinstance(subject, Topography):
                    create_kwargs["subject_topography"] = subject
                elif isinstance(subject, Tag):
                    create_kwargs["subject_tag"] = subject

                new_analysis = WorkflowResult.objects.create(**create_kwargs)

                if use_surfaces_path and isinstance(subject, Surface):
                    # M2M fields cannot be set until after the instance is created.
                    new_analysis.surfaces.set([subject])
            scheduled_dependent_analyses[key] = new_analysis
        else:
            # An analysis exists. Check whether it is successful or failed.
            # task_state is the *self reported* state, not the Celery state
            if not force and existing_analysis.task_state in [
                WorkflowResult.FAILURE,
                WorkflowResult.SUCCESS,
            ]:
                # This one does not need to be scheduled
                finished_dependent_analyses[key] = existing_analysis
            else:
                # We schedule everything else, possibly again. `perform_analysis` will
                # automatically terminate if an analysis already completed successfully.
                scheduled_dependent_analyses[key] = existing_analysis

    return (
        finished_dependent_analyses,
        scheduled_dependent_analyses,
    )
