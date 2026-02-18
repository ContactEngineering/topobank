import traceback
import tracemalloc
from typing import Any, Dict

import celery
from celery.utils.log import get_task_logger
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from muGrid.Timer import Timer
from SurfaceTopography.Support import doi

from ..manager.models import Surface, Topography
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
def schedule_workflow(self: celery.Task, analysis_id: int, force: bool):
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
    """
    from .models import WorkflowResult

    #
    # Get analysis instance from database
    #
    try:
        celery_queue = self.request.delivery_info['routing_key']
    except TypeError:
        celery_queue = None

    # Optimize query with select_related to reduce DB round trips
    analysis = WorkflowResult.objects.select_related(
        'function',
        'subject_dispatch',
        'configuration',
        'created_by',
        'owned_by'
    ).prefetch_related('permissions').get(id=analysis_id)
    _log.info(
        f"{analysis_id}/{self.request.id}: Scheduling workflow -- "
        f"Queue: {celery_queue}, force recalculation: {force} -- "
        f"Workflow: '{analysis.function.name}', subject: '{analysis.subject}', "
        f"kwargs: {analysis.kwargs}, task_state: '{analysis.task_state}'"
    )

    #
    # Check state - don't reschedule completed/failed tasks
    #
    if analysis.task_state in [WorkflowResult.FAILURE, WorkflowResult.SUCCESS] and not force:
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
                    schedule_workflow.si(dep.id, False).set(queue=celery_queue)
                    for dep in scheduled_dependencies.values()
                ),
                execute_workflow.si(analysis.id).set(queue=celery_queue),
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
        analysis.dependencies = {key: dep.id for key, dep in finished_dependencies.items()}
        analysis.save()

        # Check if any dependency failed
        if any(dep.task_state != WorkflowResult.SUCCESS for dep in finished_dependencies.values()):
            analysis.task_state = WorkflowResult.FAILURE
            analysis.task_error = "A dependent analysis failed."
            analysis.save()
            _log.debug(f"{analysis_id}/{self.request.id}: A dependency failed.")
            return

    else:
        _log.debug(f"{analysis_id}/{self.request.id}: Analysis has no dependencies.")
        analysis.dependencies = {}
        analysis.save()

    # No dependencies or all dependencies finished successfully - execute directly
    _log.debug(f"{analysis_id}/{self.request.id}: Calling execute_workflow directly.")
    execute_workflow.apply(args=(analysis.id,))


@app.task(bind=True, soft_time_limit=3600, time_limit=3700)
def execute_workflow(self: celery.Task, analysis_id: int):
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
    """
    from .models import RESULT_FILE_BASENAME, WorkflowResult

    #
    # Get analysis instance from database
    #
    analysis = WorkflowResult.objects.select_related(
        'function',
        'subject_dispatch',
        'configuration',
        'created_by',
        'owned_by'
    ).prefetch_related('permissions').get(id=analysis_id)

    _log.info(
        f"{analysis_id}/{self.request.id}: Executing workflow -- "
        f"Workflow: '{analysis.function.name}', subject: '{analysis.subject}', "
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
                analysis.task_state = WorkflowResult.FAILURE
                analysis.task_error = dep.task_error or f"Dependency '{key}' failed."
                analysis.task_traceback = dep.task_traceback
                analysis.save()
                _log.warning(
                    f"{analysis_id}/{self.request.id}: Dependency '{key}' (id={dep_id}) "
                    f"is in state '{dep.task_state}', cannot execute workflow."
                )
                return
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
        result = evaluate_function(
            dois=dois,
            progress_recorder=ProgressRecorder(self),
            timer=timer,
            finished_analyses=finished_dependencies,
        )
        size, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        save_result(result, WorkflowResult.SUCCESS, peak_memory=peak, dois=dois, timer=timer)
    except Exception as exc:
        _log.warning(
            f"{analysis_id}/{self.request.id}: Exception during evaluation: {exc}"
        )
        analysis.task_state = WorkflowResult.FAILURE
        analysis.task_traceback = traceback.format_exc().replace('\x00', '')
        analysis.task_error = str(exc).replace('\x00', '')
        analysis.save()
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
            unpublished_surfaces = Surface.objects.filter(
                publication__isnull=True
            )
    else:
        if user:
            unpublished_surfaces = Surface.objects.filter(created_by=user)
        else:
            unpublished_surfaces = Surface.objects.all()
    unpublished_topographies = Topography.objects.filter(
        surface__in=unpublished_surfaces
    )
    unpublished_analyses = WorkflowResult.objects.filter(
        subject_dispatch__topography__in=unpublished_topographies
    )

    return dict(
        num_surfaces_excluding_publications=unpublished_surfaces.count(),
        num_topographies_excluding_publications=unpublished_topographies.count(),
        num_analyses_excluding_publications=unpublished_analyses.count(),
    )


def prepare_dependency_tasks(dependencies: Dict[Any, WorkflowDefinition], force: bool, user=None, parent=None):
    from .models import WorkflowResult, WorkflowSubject

    finished_dependent_analyses = {}  # Everything that finished or failed
    scheduled_dependent_analyses = {}  # Everything that needs to be scheduled
    for key, dependency in dependencies.items():
        if key in scheduled_dependent_analyses or key in finished_dependent_analyses:
            raise RuntimeError(f"Dependency '{key}' already dependent or finished.")

        # Get analysis function
        function = dependency.function

        # Clean kwargs for dependency (fill potentially missing values)
        kwargs = function.clean_kwargs(dependency.kwargs)

        # Filter latest result
        all_results = (
            WorkflowResult.objects.filter(
                function=dependency.function,
                subject_dispatch__surface=(
                    dependency.subject
                    if isinstance(dependency.subject, Surface)
                    else None
                ),
                subject_dispatch__topography=(
                    dependency.subject
                    if isinstance(dependency.subject, Topography)
                    else None
                ),
                kwargs=kwargs,
            )
            .select_related('function', 'subject_dispatch')  # Optimize DB queries
            .order_by(
                "subject_dispatch__topography_id",
                "subject_dispatch__surface_id",
                "subject_dispatch__tag_id",
                "-task_start_time",
            )
            .distinct(
                "subject_dispatch__topography_id",
                "subject_dispatch__surface_id",
                "subject_dispatch__tag_id",
            )
        )

        # Cache count to avoid multiple queries
        results_count = all_results.count()
        if results_count == 0:
            with transaction.atomic():
                # Create new entry in the analysis table
                new_analysis = WorkflowResult.objects.create(
                    permissions=parent.permissions,
                    subject_dispatch=WorkflowSubject.objects.create(dependency.subject),
                    function=function,
                    task_state=WorkflowResult.PENDING,  # We are submitting this right away
                    kwargs=kwargs,
                    created_by=user,
                    owned_by=parent.owned_by,
                )
            scheduled_dependent_analyses[key] = new_analysis
        elif results_count == 1:
            # An analysis exists. Check whether it is successful or failed.
            existing_analysis = all_results.first()
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
        else:
            # More than one analysis exists. This should not happen.
            raise RuntimeError("More than one analysis found for dependency.")

    return (
        finished_dependent_analyses,
        scheduled_dependent_analyses,
    )
