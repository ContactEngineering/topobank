import logging
import traceback
import tracemalloc
from datetime import date
from typing import Any, Dict

import celery
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from SurfaceTopography.Support import doi
from trackstats.models import Period, StatisticByDate, StatisticByDateAndObject

from ..authorization.models import PermissionSet
from ..files.models import Folder
from ..manager.models import Surface, Topography
from ..supplib.dict import store_split_dict
from ..taskapp.celeryapp import app
from ..taskapp.models import Configuration
from ..taskapp.tasks import ProgressRecorder
from ..taskapp.utils import get_package_version
from .workflows import WorkflowDefinition

_log = logging.getLogger(__name__)


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


@app.task(bind=True)
def perform_analysis(self, analysis_id: int, force: bool):
    """Perform an analysis which is already present in the database.

    Parameters
    ----------
    self : celery.app.task.Task
        Celery task on execution (because of bind=True).
    analysis_id : int
        ID of `topobank.analysis.Analysis` instance.
    force : bool
        Submission was forced, which means we need to renew dependencies.

    Also alters analysis instance in database saving

    - result (wanted or exception)
    - start time on start
    - end time on finish
    - task_id
    - task_state
    - current configuration (link to versions of installed dependencies)
    """
    from .models import RESULT_FILE_BASENAME, WorkflowResult

    _log.debug(f"{analysis_id}/{self.request.id}: Task for workflow started...")

    #
    # Get analysis instance from database
    #
    analysis = WorkflowResult.objects.get(id=analysis_id)
    _log.info(
        f"{analysis_id}/{self.request.id}: Function: '{analysis.function.name}', "
        f"subject: '{analysis.subject}', kwargs: {analysis.kwargs}, "
        f"task_state: '{analysis.task_state}', force: {force}"
    )

    #
    # Check state
    #
    if analysis.task_state in [WorkflowResult.FAILURE, WorkflowResult.SUCCESS] and not force:
        # Do not rerun this task as it is self-reporting to either have completed
        # successfully or to have failed.
        s = (
            "completed successfully"
            if analysis.task_state == WorkflowResult.SUCCESS
            else "failed"
        )
        _log.debug(
            f"{self.request.id}: Terminating analysis task because this analysis has "
            f"{s} in a previous run."
        )
        return

    #
    # Update entry in Analysis table to indicate we started processing it
    #
    analysis.task_state = WorkflowResult.STARTED
    analysis.task_id = self.request.id
    analysis.task_start_time = timezone.now()  # with timezone
    analysis.configuration = get_current_configuration()

    #
    # Check and run dependencies
    #
    dependencies = analysis.function.get_dependencies(analysis)  # This is a dict!
    finished_dependencies = {}  # Will contain dependencies that finished
    if len(dependencies) > 0:
        # Okay, we have dependencies so let us check what their states are
        _log.debug(f"{self.request.id}: Checking analysis dependencies...")
        finished_dependencies, scheduled_dependencies = prepare_dependency_tasks(
            dependencies, force
        )
        if len(scheduled_dependencies) > 0:
            # We just created new `Analysis` instances or decided that an existing
            # analysis needs to be scheduled. Submit Celery tasks for all
            # dependencies and request that this task is rerun once all dependencies
            # have finished.
            for dep in scheduled_dependencies.values():
                dep.set_pending_state()
            # Store dependencies
            analysis.dependencies = {
                key: dep.id for key, dep in scheduled_dependencies.items()
            }
            # We are about to launch a chord, store id as launcher id
            analysis.launcher_task_id = self.request.id
            # Save because apply_async never returns in test when a dependency fails
            analysis.save()
            task = celery.chord(
                (
                    perform_analysis.si(dep.id, False)
                    for dep in scheduled_dependencies.values()
                ),
                perform_analysis.si(analysis.id, False),
            ).apply_async()
            # Store task id so it is reported as pending
            analysis.task_id = task.id
            analysis.save(update_fields=["task_id"])
            _log.debug(
                f"{analysis_id}/{self.request.id}: Submitted "
                f"{len(scheduled_dependencies)} dependencies; finishing the current "
                "task until dependencies are resolved."
            )
            return
    else:
        _log.debug(f"{analysis_id}/{self.request.id}: Analysis has no dependencies.")

    # Store dependencies
    analysis.dependencies = {key: dep.id for key, dep in finished_dependencies.items()}

    # Check if any dependency failed
    if any(
            dep.task_state != WorkflowResult.SUCCESS for dep in finished_dependencies.values()
    ):
        analysis.task_state = WorkflowResult.FAILURE
        analysis.task_error = "A dependent analysis failed."
        analysis.save()
        # We return here because a dependency failed
        return

    # Save analysis
    analysis.save()

    def save_result(result, task_state, peak_memory=None, dois=set()):
        analysis.task_state = task_state
        store_split_dict(analysis.folder, RESULT_FILE_BASENAME, result)
        analysis.end_time = timezone.now()  # with timezone
        analysis.task_memory = peak_memory
        analysis.dois = list(dois)  # dois is a set, we need to convert it
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
    def evaluate_function(progress_recorder, finished_analyses):
        if len(finished_analyses) > 0:
            return analysis.eval_self(
                dependencies=finished_analyses,
                progress_recorder=progress_recorder,
            )
        else:
            return analysis.eval_self(
                progress_recorder=progress_recorder,
            )

    #
    # We are good: Actually perform the analysis
    #
    _log.debug(
        f"{analysis_id}/{self.request.id}: Starting evaluation of analysis function..."
    )
    try:
        # also request citation information
        dois = set()
        # start tracing of memory usage
        tracemalloc.start()
        tracemalloc.reset_peak()
        # run actual function
        result = evaluate_function(
            dois=dois,
            progress_recorder=ProgressRecorder(self),
            finished_analyses=finished_dependencies,
        )
        # collect memory usage
        size, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        save_result(result, WorkflowResult.SUCCESS, peak_memory=peak, dois=dois)
    except Exception as exc:
        _log.warning(
            f"{analysis_id}/{self.request.id}: Exception during evaluation: {exc}"
        )
        analysis.task_state = WorkflowResult.FAILURE
        analysis.task_traceback = traceback.format_exc()
        # Store string representation of exception as user-reported error string
        analysis.task_error = str(exc)
        analysis.save()
        # We want a real exception here so celery's flower can show the task as failure
        raise
    finally:
        try:
            #
            # First check whether analysis is still there
            #
            analysis = WorkflowResult.objects.get(id=analysis_id)
        except WorkflowResult.DoesNotExist:
            _log.debug(
                f"{analysis_id}/{self.request.id}: Analysis {analysis_id} does not exist."
            )
            # Analysis was deleted, e.g. because topography or surface was missing, we
            # simply ignore this case.
            pass
        else:
            #
            # Analysis exists, record end time
            #
            analysis.task_end_time = timezone.now()  # with timezone
            analysis.save(update_fields=["task_end_time"])
            #
            # Add up number of seconds for CPU time
            #
            from trackstats.models import Metric

            td = analysis.task_duration
            if td is not None:
                increase_statistics_by_date(
                    metric=Metric.objects.TOTAL_ANALYSIS_CPU_MS,
                    increment=1000 * td.total_seconds(),
                )
                increase_statistics_by_date_and_object(
                    metric=Metric.objects.TOTAL_ANALYSIS_CPU_MS,
                    obj=analysis.function,
                    increment=1000 * td.total_seconds(),
                )
            else:
                _log.warning(
                    f"{analysis_id}/{self.request.id}: Duration of task could not be "
                    "computed."
                )
    _log.debug(f"{analysis_id}/{self.request.id}: Task finished normally.")


@transaction.atomic
def increase_statistics_by_date(metric, period=Period.DAY, increment=1):
    """Increase statistics by date in database using the current date.

    Initializes statistics by date to given increment, if it does not
    exist.

    Parameters
    ----------
    metric: trackstats.models.Metric object

    period: trackstats.models.Period object, optional
        Examples: Period.LIFETIME, Period.DAY
        Defaults to Period.DAY, i.e. store
        incremental values on a daily basis.

    increment: int, optional
        How big the the increment, default to 1.


    Returns
    -------
        None
    """
    if not settings.ENABLE_USAGE_STATS:
        return

    today = date.today()

    if StatisticByDate.objects.filter(
        metric=metric, period=period, date=today
    ).exists():
        # we need this if-clause, because F() expressions
        # only works on updates but not on inserts
        StatisticByDate.objects.record(
            date=today, metric=metric, value=F("value") + increment, period=period
        )
    else:
        StatisticByDate.objects.record(
            date=today, metric=metric, value=increment, period=period
        )


@transaction.atomic
def increase_statistics_by_date_and_object(metric, obj, period=Period.DAY, increment=1):
    """Increase statistics by date in database using the current date.

    Initializes statistics by date to given increment, if it does not
    exist.

    Parameters
    ----------
    metric: trackstats.models.Metric object

    obj: any class for which a contenttype exists, e.g. Topography
        Some object for which this metric should be increased.
    period: trackstats.models.Period object, optional
        Examples: Period.LIFETIME, Period.DAY
        Defaults to Period.DAY, i.e. store
        incremental values on a daily basis.

    increment: int, optional
        How big the the increment, default to 1.


    Returns
    -------
        None
    """
    if not settings.ENABLE_USAGE_STATS:
        return

    today = date.today()

    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(obj)

    at_least_one_entry_exists = StatisticByDateAndObject.objects.filter(
        metric=metric, period=period, date=today, object_id=obj.id, object_type_id=ct.id
    ).exists()

    if at_least_one_entry_exists:
        # we need this if-clause, because F() expressions
        # only works on updates but not on inserts
        StatisticByDateAndObject.objects.record(
            date=today,
            metric=metric,
            object=obj,
            value=F("value") + increment,
            period=period,
        )
    else:
        StatisticByDateAndObject.objects.record(
            date=today, metric=metric, object=obj, value=increment, period=period
        )


def current_statistics(user=None):
    """Return some statistics about managed data.

    These values are calculated from current counts
    of database objects.

    Parameters
    ----------
        user: User instance
            If given, the statistics is only related to the surfaces of a given user
            (as creator)

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
                creator=user, publication__isnull=True, deletion_time__isnull=True
            )
        else:
            unpublished_surfaces = Surface.objects.filter(
                publication__isnull=True, deletion_time__isnull=True
            )
    else:
        if user:
            unpublished_surfaces = Surface.objects.filter(
                creator=user, deletion_time__isnull=True
            )
        else:
            unpublished_surfaces = Surface.objects.filter(deletion_time__isnull=True)
    unpublished_topographies = Topography.objects.filter(
        surface__in=unpublished_surfaces, deletion_time__isnull=True
    )
    unpublished_analyses = WorkflowResult.objects.filter(
        subject_dispatch__topography__in=unpublished_topographies
    )

    return dict(
        num_surfaces_excluding_publications=unpublished_surfaces.count(),
        num_topographies_excluding_publications=unpublished_topographies.count(),
        num_analyses_excluding_publications=unpublished_analyses.count(),
    )


def prepare_dependency_tasks(dependencies: Dict[Any, WorkflowDefinition], force: bool):
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

        if all_results.count() == 0:
            # No analysis exists, we create a new one.
            # New analysis needs its own permissions
            permissions = PermissionSet.objects.create()
            # Nobody can formally access this analysis, but access will be granted
            # automatically when requesting it directly (through the GET route)

            # Folder will store any resulting files
            folder = Folder.objects.create(permissions=permissions, read_only=True)

            # Create new entry in the analysis table
            new_analysis = WorkflowResult.objects.create(
                permissions=permissions,
                subject_dispatch=WorkflowSubject.objects.create(dependency.subject),
                function=function,
                task_state=WorkflowResult.PENDING,  # We are submitting this right away
                kwargs=kwargs,
                folder=folder,
            )
            scheduled_dependent_analyses[key] = new_analysis
        elif all_results.count() == 1:
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
