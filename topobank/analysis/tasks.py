import json
import traceback
from typing import Any, Dict

import celery
from celery.utils.log import get_task_logger
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone
from muTimer import Timer
from SurfaceTopography.Support import doi

from ..manager.models import Surface, Tag, Topography
from ..supplib.db import advisory_lock
from ..supplib.dict import store_split_dict
from ..taskapp.celeryapp import app
from ..taskapp.memory import track_memory_usage
from ..taskapp.models import Configuration
from ..taskapp.tasks import ProgressRecorder
from ..taskapp.utils import get_package_version
from .sizing import check_memory_budget
from .workflows import WorkflowDefinition

_log = get_task_logger(__name__)

# Time limits for the workflow tasks below. Long-running workflows (e.g. model
# training) can exceed a fixed one-hour budget, so the limits are taken from
# the standard Celery settings where deployments tune them. Falls back to a
# 6-hour hard limit (soft limit 5 minutes earlier for graceful cleanup) when
# the settings are absent or Django settings are not configured.
DEFAULT_TASK_TIME_LIMIT = 21600  # 6 hours
DEFAULT_TASK_SOFT_TIME_LIMIT = DEFAULT_TASK_TIME_LIMIT - 300

try:
    TASK_SOFT_TIME_LIMIT = getattr(
        settings, "CELERY_TASK_SOFT_TIME_LIMIT", DEFAULT_TASK_SOFT_TIME_LIMIT
    )
    TASK_TIME_LIMIT = getattr(settings, "CELERY_TASK_TIME_LIMIT", DEFAULT_TASK_TIME_LIMIT)
except ImproperlyConfigured:
    TASK_SOFT_TIME_LIMIT = DEFAULT_TASK_SOFT_TIME_LIMIT
    TASK_TIME_LIMIT = DEFAULT_TASK_TIME_LIMIT


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

    # Serialize the check-then-create so concurrent workers (e.g. right after a
    # dependency version bump) do not each create a redundant Configuration for
    # the same version set. Doing the create and versions.set() inside one
    # transaction also means a Configuration is never observed with an empty
    # versions set. The advisory lock is released when the transaction commits.
    current_version_ids = set(v.id for v in versions)
    with transaction.atomic(), advisory_lock("current-configuration"):
        if Configuration.objects.count() == 0:
            return make_config_from_versions()

        # Find out whether the latest configuration has exactly these versions
        latest_config = Configuration.objects.latest("valid_since")
        latest_version_ids = set(v.id for v in latest_config.versions.all())

        if current_version_ids == latest_version_ids:
            return latest_config
        else:
            return make_config_from_versions()


@app.task(bind=True, soft_time_limit=TASK_SOFT_TIME_LIMIT, time_limit=TASK_TIME_LIMIT)
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
        failed_dependencies = [
            dep
            for dep in finished_dependencies.values()
            if dep.task_state != WorkflowResult.SUCCESS
        ]
        if failed_dependencies:
            # Surface the failed dependency's real error/traceback on the parent
            # rather than a generic message, so the UI shows why it failed
            # (mirrors execute_workflow and _fail_parent_on_dependency_failure).
            failed_dep = failed_dependencies[0]
            analysis.task_state = WorkflowResult.FAILURE
            analysis.task_error = failed_dep.task_error or "A dependent analysis failed."
            analysis.task_traceback = failed_dep.task_traceback
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
        args=(analysis.id, is_dependency),
        kwargs={"parent_id": parent_id, "queue": celery_queue},
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


# How often, and how long in total, execute_workflow waits for a dependency
# that is not finished when the run is due (see there). The limit covers a
# long dependency computed by another run; a dependency whose worker died is
# failed by the lost-task sweep, and then this run fails with its error.
DEPENDENCY_WAIT_INTERVAL = 30  # seconds
DEPENDENCY_WAIT_LIMIT = 6 * 3600  # seconds

_STATE_WORDS = {
    "no": "not started",
    "pe": "pending",
    "pd": "waiting for its own dependencies",
    "st": "running",
    "re": "being retried",
}


def _read_dependencies(analysis):
    """The dependencies of *analysis* as a list of (key, id, WorkflowResult),
    read in one query; the WorkflowResult is None for a deleted dependency.

    execute_workflow decides whether to wait and what to load from this single
    read, so a dependency renewed in between cannot be loaded as unfinished.
    Integer-like keys are converted back to int: JSON only has string keys, but
    workflows index dependencies by e.g. surface.id.
    """
    from .models import WorkflowResult

    if not analysis.dependencies:
        return []
    rows = WorkflowResult.objects.in_bulk(list(analysis.dependencies.values()))
    deps = []
    for key, dep_id in analysis.dependencies.items():
        try:
            key = int(key)
        except ValueError:
            pass  # Keep as string if not a valid integer
        deps.append((key, dep_id, rows.get(dep_id)))
    return deps


def _update_unless_superseded(analysis, **fields):
    """Write *fields* to the row of *analysis* only if its state and task id are
    still the ones this run read. Returns whether the row was updated.

    Between that read and this write, a dependency's worker can fail the parent
    (_fail_parent_on_dependency_failure) or a resubmission can take the row
    over with a new task id; a stale run must not undo either.
    """
    from .models import WorkflowResult

    return bool(
        WorkflowResult.objects.filter(
            pk=analysis.pk,
            task_state=analysis.task_state,
            task_id=analysis.task_id,
        ).update(**fields)
    )


@app.task(bind=True, soft_time_limit=TASK_SOFT_TIME_LIMIT, time_limit=TASK_TIME_LIMIT)
def execute_workflow(
    self: celery.Task,
    analysis_id: int,
    is_dependency: bool = False,
    parent_id: int = None,
    waited: int = 0,
    queue: str = None,
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
    waited : int, optional
        Seconds this run has already waited for unfinished dependencies (see
        the dependency check below). (Default: 0)
    queue : str, optional
        Queue to re-queue on while waiting, when the request does not carry
        one: schedule_workflow runs this task with ``.apply()``. (Default: None)
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
    # Check the dependencies, from a single read (_read_dependencies), before
    # marking this run STARTED:
    # - A failed (or deleted) dependency fails this run with its error. This is
    #   checked first, so another, unfinished dependency cannot mask it.
    # - An unfinished one is waited for. The chord fires when *its* header tasks
    #   are done, but a shared dependency can be pending or running again by
    #   then: another parent's forced submit renews it in place
    #   (prepare_dependency_tasks). Failing here reported "Dependency 'x'
    #   failed." for a dependency that went on to succeed. Re-queue instead,
    #   still PENDING_DEPENDENCIES (the lost-task sweep only reaps STARTED rows).
    # All writes here are guarded (_update_unless_superseded).
    #
    dependencies = _read_dependencies(analysis)

    def fail_before_start(error_msg, traceback=None):
        if not _update_unless_superseded(
            analysis,
            task_state=WorkflowResult.FAILURE,
            task_error=error_msg,
            task_traceback=traceback,
            task_end_time=timezone.now(),
        ):
            _log.info(
                "%s/%s: Not failing this run (%s): the workflow changed state "
                "or was submitted again meanwhile.",
                analysis_id,
                self.request.id,
                error_msg,
            )
            return
        # Raise so Celery reports task_failure (not task_success)
        raise RuntimeError(error_msg)

    for key, dep_id, dep in dependencies:
        if dep is None:
            _log.warning(
                "%s/%s: Dependency '%s' (id=%s) no longer exists.",
                analysis_id,
                self.request.id,
                key,
                dep_id,
            )
            return fail_before_start(
                f"Dependency '{key}' (#{dep_id}) no longer exists. "
                "Submit this workflow again."
            )
        if dep.task_state == WorkflowResult.FAILURE:
            # Copy error and traceback from the failed dependency
            _log.warning(
                "%s/%s: Dependency '%s' (id=%s) failed, cannot execute workflow.",
                analysis_id,
                self.request.id,
                key,
                dep_id,
            )
            return fail_before_start(
                dep.task_error
                or (
                    f"Dependency '{key}' ({dep.workflow_name} #{dep.id}) failed "
                    "without an error message."
                ),
                dep.task_traceback,
            )

    unfinished = next(
        (
            (key, dep)
            for key, _, dep in dependencies
            if dep.task_state != WorkflowResult.SUCCESS
        ),
        None,
    )
    if unfinished is not None:
        key, dep = unfinished
        # Not request.is_eager: schedule_workflow runs this task with .apply()
        # on real workers too, where a countdown is honoured. Only with
        # task_always_eager is it ignored, and re-queueing would recurse.
        if self.app.conf.task_always_eager or waited >= DEPENDENCY_WAIT_LIMIT:
            return fail_before_start(
                f"Dependency '{key}' ({dep.workflow_name} #{dep.id}) was still "
                f"{_STATE_WORDS.get(dep.task_state, dep.task_state)} when this "
                "workflow was due to start, probably because another run "
                "submitted it again. Submit this workflow again."
            )
        # Claim the row for the re-queued task before publishing it, so a stale
        # run neither re-opens a parent that failed meanwhile nor takes over a
        # resubmission's row (and publishes nothing).
        next_task_id = celery.uuid()
        if not _update_unless_superseded(
            analysis,
            task_state=WorkflowResult.PENDING_DEPENDENCIES,
            task_id=next_task_id,
        ):
            _log.info(
                "%s/%s: Not waiting for dependency '%s': the workflow changed "
                "state or was submitted again meanwhile.",
                analysis_id,
                self.request.id,
                key,
            )
            return
        _log.info(
            "%s/%s: Dependency '%s' (id=%s) is in state '%s'; waiting %ss.",
            analysis_id,
            self.request.id,
            key,
            dep.id,
            dep.task_state,
            DEPENDENCY_WAIT_INTERVAL,
        )
        # Under .apply() the request has no routing key; keep the queue passed
        # by schedule_workflow then.
        queue = (self.request.delivery_info or {}).get("routing_key") or queue
        execute_workflow.apply_async(
            args=(analysis_id, is_dependency),
            kwargs={
                "parent_id": parent_id,
                "waited": waited + DEPENDENCY_WAIT_INTERVAL,
                "queue": queue,
            },
            countdown=DEPENDENCY_WAIT_INTERVAL,
            queue=queue,
            task_id=next_task_id,
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

    # All dependencies succeeded (checked above, from the same read)
    finished_dependencies = {key: dep for key, _, dep in dependencies}

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
    # Created outside the try so the failure path below can persist whatever
    # block durations were recorded before the exception (Timer records in a
    # finally, so an interrupted block — e.g. a SoftTimeLimitExceeded mid
    # LOO fold — still leaves its partial duration behind).
    timer = Timer(str(self.request.id))
    try:
        # Refuse an analysis that cannot fit before allocating anything. The
        # alternative is the OOM killer removing this process mid-computation,
        # which leaves the user with no explanation and (when the whole container
        # goes) a row stuck in "running". Raising here instead means the handler
        # below records a FAILURE carrying a message the user can act on.
        check_memory_budget(analysis)

        dois = set()
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

        # Peak-memory tracking: cheap RSS high-water mark by default;
        # precise (but ~35x slower on numeric workloads) tracemalloc only
        # when TOPOBANK_TRACK_MEMORY_USAGE is enabled. See taskapp/memory.py.
        with track_memory_usage() as memory_usage:
            result = evaluate_function(
                dois=dois,
                progress_recorder=ProgressRecorder(self, on_progress=on_progress),
                timer=timer,
                finished_analyses=finished_dependencies,
            )
        save_result(
            result,
            WorkflowResult.SUCCESS,
            peak_memory=memory_usage.peak,
            dois=dois,
            timer=timer,
        )
    except Exception as exc:
        _log.exception(
            f"{analysis_id}/{self.request.id}: Exception during evaluation: {exc}"
        )
        analysis.task_state = WorkflowResult.FAILURE
        analysis.task_traceback = traceback.format_exc().replace("\x00", "")
        analysis.task_error = str(exc).replace("\x00", "")
        # Persist the timings recorded up to the failure: for timeouts this is
        # what distinguishes "one stage stalled for an hour" from "many stages,
        # each fast, exceeded the budget together". muTimer records in a
        # finally, so the interrupted block carries its partial duration.
        timer_dict = timer.to_dict()
        if timer_dict.get("timers"):
            analysis.task_timer = timer_dict
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
@app.task(bind=True, soft_time_limit=TASK_SOFT_TIME_LIMIT, time_limit=TASK_TIME_LIMIT)
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
        # Serialize the existence check and creation of this dependency against
        # concurrent parents needing the same dependency. Without this, two
        # parents can both observe "no existing dependency" and each create a
        # separate dependency analysis, doubling the work. The advisory lock is
        # released when the surrounding transaction commits.
        with transaction.atomic(), advisory_lock(
            "dependency",
            function.name,
            subject_hash,
            json.dumps(kwargs, sort_keys=True, default=str),
        ):
            existing_analysis = existing_analysis_qs.order_by(
                "-task_start_time"
            ).first()

            if existing_analysis is None:
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
                    # We schedule everything else, possibly again.
                    # `perform_analysis` will automatically terminate if an
                    # analysis already completed successfully.
                    scheduled_dependent_analyses[key] = existing_analysis

    return (
        finished_dependent_analyses,
        scheduled_dependent_analyses,
    )
