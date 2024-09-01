import logging
import traceback
import tracemalloc
from datetime import date

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from SurfaceTopography.Support import doi
from trackstats.models import Period, StatisticByDate, StatisticByDateAndObject

from ..manager.models import Surface, Topography
from ..supplib.dict import store_split_dict
from ..taskapp.celeryapp import app
from ..taskapp.models import Configuration
from ..taskapp.tasks import ProgressRecorder
from ..taskapp.utils import get_package_version

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

    _log.debug(f"Starting task {self.request.id} for analysis {analysis_id}...")
    progress_recorder = ProgressRecorder(self)

    #
    # update entry in Analysis table
    #
    analysis = Analysis.objects.get(id=analysis_id)

    analysis.task_state = Analysis.STARTED
    analysis.task_id = self.request.id
    analysis.start_time = timezone.now()  # with timezone
    analysis.configuration = get_current_configuration()
    analysis.save()

    def save_result(result, task_state, peak_memory=None, dois=set()):
        if peak_memory is not None:
            _log.debug(
                f"Saving result of analysis {analysis_id} with task state "
                f"'{task_state}' and peak memory usage of "
                f"{int(peak_memory / 1024 / 1024)} MB to storage..."
            )
        else:
            _log.debug(
                f"Saving result of analysis {analysis_id} with task state "
                f"'{task_state}'..."
            )
        analysis.task_state = task_state
        store_split_dict(analysis.storage_prefix, RESULT_FILE_BASENAME, result)
        analysis.end_time = timezone.now()  # with timezone
        analysis.task_memory = peak_memory
        analysis.dois = list(dois)  # dois is a set, we need to convert it
        analysis.save()

    @doi()
    def evaluate_function(progress_recorder, storage_prefix, kwargs):
        return analysis.eval_self(
            progress_recorder=progress_recorder,
            storage_prefix=storage_prefix,
            kwargs=kwargs,
        )

    #
    # actually perform the analysis
    #
    kwargs = analysis.kwargs
    subject = analysis.subject
    _log.debug(
        f"Evaluating analysis function '{analysis.function.name}' on subject "
        f"'{subject}' with parameters {kwargs}..."
    )
    try:
        # tell subject to restrict to specific user
        subject.authorize_user(analysis.user, "view")
        # also request citation information
        dois = set()
        # start tracing of memory usage
        tracemalloc.start()
        tracemalloc.reset_peak()
        # run actual function
        result = evaluate_function(
            progress_recorder=progress_recorder,
            storage_prefix=analysis.storage_prefix,
            dois=dois,
            kwargs=kwargs,
        )
        # collect memory usage
        size, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        _log.debug(
            f"Analysis function '{analysis.function.name}' on subject '{subject}' "
            "evaluated without error; peak memory usage was "
            f"{int(peak / 1024 / 1024)} MB."
        )
        save_result(result, Analysis.SUCCESS, peak_memory=peak, dois=dois)
    except Exception as exc:
        _log.warning(
            f"Exception while evaluating analysis function '{analysis.function.name}' "
            f"on subject '{subject}': {exc}"
        )
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
                    f"Duration for analysis with {analysis_id} could not be computed."
                )

        except Analysis.DoesNotExist:
            _log.debug(f"Analysis {analysis_id} does not exist.")
            # Analysis was deleted, e.g. because topography or surface was missing, we
            # simply ignore this case.
            pass
    _log.debug(f"Task {self.request.id} finished.")


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
