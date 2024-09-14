import logging
import traceback
import tracemalloc
from datetime import date

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
from .functions import AnalysisInputData

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
def perform_analysis(self, analysis_id: int):
    """Perform an analysis which is already present in the database.

    Parameters
    ----------
    self : celery.app.task.Task
        Celery task on execution (because of bind=True)
    analysis_id : int
        ID of Analysis entry in database

    Also alters analysis instance in database saving

    - result (wanted or exception)
    - start time on start
    - end time on finish
    - task_id
    - task_state
    - current configuration (link to versions of installed dependencies)
    """
    from .models import RESULT_FILE_BASENAME, Analysis

    _log.debug(f"{self.request.id}: Task for analysis {analysis_id} started...")
    progress_recorder = ProgressRecorder(self)

    #
    # Check analysis dependencies
    #
    analysis = Analysis.objects.get(id=analysis_id)
    _log.debug(
        f"{self.request.id}: Function: '{analysis.function.name}', "
        f"subject: '{analysis.subject}', kwargs: {analysis.kwargs}"
    )

    # Get parameters for all dependencies
    dependencies = analysis.function.get_dependencies(analysis)
    finished_dependencies = []  # Will contain dependencies that finished
    if len(dependencies) > 0:
        # Okay, we have dependencies so let us check what their states are
        _log.debug(f"{self.request.id}: Checking analysis dependencies...")
        finished_dependencies, pending_dependencies, created_dependencies = (
            prepare_dependency_tasks(analysis, dependencies)
        )
        if len(created_dependencies) > 0:
            # We just created new `Analysis` instances for dependencies. Those tasks
            # are not yet running. Submit dependencies and request that this task is
            # rerun once all dependencies have finished.
            celery.chord(
                (perform_analysis.si(dep.id) for dep in created_dependencies),
                perform_analysis.si(analysis.id),
            ).apply_async()
            _log.debug(
                f"{self.request.id}: Submitted {len(created_dependencies)} "
                "dependencies; finishing the current task until dependencies are "
                "resolved."
            )
            return
        if len(pending_dependencies) > 0:
            # There are dependencies that are in state pending or running, but that
            # were not started by us because otherwise they would have run as part of
            # the chord above. This can happen is another user is simultaneously
            # requesting the same analyses. In this case, we suspend the task for
            # 30 seconds and then check again.
            _log.debug(
                f"{self.request.id}: There are {len(pending_dependencies)} "
                "pending dependencies. Suspending the current task for 30 seconds to "
                "wait for completion."
            )
            for dep in pending_dependencies:
                _log.debug(
                    f"{self.request.id}:    Dependent analysis: {dep.id}, task id: "
                    f"{dep.task_id}, task state: '{dep.task_state}', created: "
                    f"{dep.creation_time}, started: {dep.start_time}, finished: "
                    f"{dep.end_time}"
                )
            _log.debug(
                f"{self.request.id}: Resubmitting analysis {analysis.id} and "
                "terminating task."
            )
            perform_analysis.apply_async(args=(analysis.id,), countdown=30)
            return
    else:
        _log.debug(f"{self.request.id}: Analysis has no dependencies.")

    #
    # update entry in Analysis table
    #
    analysis.task_state = Analysis.STARTED
    analysis.task_id = self.request.id
    analysis.start_time = timezone.now()  # with timezone
    analysis.configuration = get_current_configuration()
    analysis.save()

    def save_result(result, task_state, peak_memory=None, dois=set()):
        if peak_memory is not None:
            _log.debug(
                f"{self.request.id}: Task state '{task_state}', peak memory usage: "
                f"{int(peak_memory / 1024 / 1024)} MB; saving results..."
            )
        else:
            _log.debug(
                f"{self.request.id}: Task state '{task_state}'; saving results..."
            )
        analysis.task_state = task_state
        store_split_dict(analysis.folder, RESULT_FILE_BASENAME, result)
        analysis.end_time = timezone.now()  # with timezone
        analysis.task_memory = peak_memory
        analysis.dois = list(dois)  # dois is a set, we need to convert it
        analysis.save()

    @doi()
    def evaluate_function(progress_recorder, kwargs, finished_analyses):
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
    # actually perform the analysis
    #
    kwargs = analysis.kwargs
    _log.debug(f"{self.request.id}: Starting evaluation of analysis function...")
    try:
        # also request citation information
        dois = set()
        # start tracing of memory usage
        tracemalloc.start()
        tracemalloc.reset_peak()
        # run actual function
        result = evaluate_function(
            dois=dois,
            progress_recorder=progress_recorder,
            kwargs=kwargs,
            finished_analyses=finished_dependencies,
        )
        # collect memory usage
        size, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        _log.debug(
            f"{self.request.id}: Evaluation finished without error; peak memory usage: "
            f"{int(peak / 1024 / 1024)} MB"
        )
        save_result(result, Analysis.SUCCESS, peak_memory=peak, dois=dois)
    except Exception as exc:
        _log.warning(f"{self.request.id}: Exception during evaluation: {exc}")
        save_result(
            dict(error=str(exc), traceback=traceback.format_exc()), Analysis.FAILURE
        )
        # we want a real exception here so celery's flower can show the task as failure
        raise
    finally:
        try:
            #
            # first check whether analysis is still there
            #
            analysis = Analysis.objects.get(id=analysis_id)

            #
            # Add up number of seconds for CPU time
            #
            from trackstats.models import Metric

            td = analysis.duration
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
                    f"{self.request.id}: Duration of task could not be computed."
                )

        except Analysis.DoesNotExist:
            _log.debug(f"{self.request.id}: Analysis {analysis_id} does not exist.")
            # Analysis was deleted, e.g. because topography or surface was missing, we
            # simply ignore this case.
            pass
    _log.debug(f"{self.request.id}: Task finished.")


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
    from .models import Analysis

    if hasattr(Surface, "publication"):
        if user:
            unpublished_surfaces = Surface.objects.filter(
                creator=user, publication__isnull=True
            )
        else:
            unpublished_surfaces = Surface.objects.filter(publication__isnull=True)
    else:
        if user:
            unpublished_surfaces = Surface.objects.filter(creator=user)
        else:
            unpublished_surfaces = Surface.objects.all()
    unpublished_topographies = Topography.objects.filter(
        surface__in=unpublished_surfaces
    )
    unpublished_analyses = Analysis.objects.filter(
        subject_dispatch__topography__in=unpublished_topographies
    )

    return dict(
        num_surfaces_excluding_publications=unpublished_surfaces.count(),
        num_topographies_excluding_publications=unpublished_topographies.count(),
        num_analyses_excluding_publications=unpublished_analyses.count(),
    )


def prepare_dependency_tasks(analysis: int, dependencies: list[AnalysisInputData]):
    from .models import Analysis, AnalysisSubject

    finished_dependent_analyses = []  # Everything that finished or failed
    pending_dependent_analyses = []  # Everything that is pending or running
    created_dependent_analyses = []  # Everything that has not yet been scheduled
    for dependency in dependencies:
        # Get analysis function
        function = dependency.function
        kwargs = function.clean_kwargs(dependency.kwargs)

        # Filter latest result
        all_results = (
            Analysis.objects.filter(
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
                "-start_time",
            )
            .distinct(
                "subject_dispatch__topography_id",
                "subject_dispatch__surface_id",
                "subject_dispatch__tag_id",
            )
        )

        if all_results.count() == 0:
            # New analysis needs its own permissions
            permissions = PermissionSet.objects.create()
            # Nobody can formally access this analysis, but access will be granted
            # automatically when requesting it directly (through the GET route)

            # Folder will store results
            folder = Folder.objects.create(permissions=permissions, read_only=True)

            # Create new entry in the analysis table
            dependent_analysis = Analysis.objects.create(
                permissions=permissions,
                subject_dispatch=AnalysisSubject.objects.create(dependency.subject),
                function=function,
                task_state=Analysis.PENDING,
                kwargs=kwargs,
                folder=folder,
            )
            created_dependent_analyses += [dependent_analysis]
        elif all_results.count() == 1:
            dependent_analysis = all_results.first()
            if dependent_analysis.task_state in [Analysis.PENDING, Analysis.STARTED]:
                pending_dependent_analyses += [dependent_analysis]
            else:
                finished_dependent_analyses += [dependent_analysis]

    return (
        finished_dependent_analyses,
        pending_dependent_analyses,
        created_dependent_analyses,
    )
