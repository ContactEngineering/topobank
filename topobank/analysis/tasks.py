import logging
import traceback
import tracemalloc

from django.conf import settings
from django.utils import timezone
from SurfaceTopography.Support import doi

from ..supplib.dict import store_split_dict
from ..taskapp.celeryapp import app
from ..taskapp.tasks import ProgressRecorder
from ..taskapp.utils import get_package_version
from ..usage_stats.utils import (
    increase_statistics_by_date,
    increase_statistics_by_date_and_object,
)
from .models import RESULT_FILE_BASENAME, Analysis, Configuration

_log = logging.getLogger(__name__)


def current_configuration():
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
    _log.debug(f"Starting task {self.request.id} for analysis {analysis_id}..")
    progress_recorder = ProgressRecorder(self)

    #
    # update entry in Analysis table
    #
    analysis = Analysis.objects.get(id=analysis_id)

    analysis.task_state = Analysis.STARTED
    analysis.task_id = self.request.id
    analysis.start_time = timezone.now()  # with timezone
    analysis.configuration = current_configuration()
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
    # actually perform analysis
    #
    try:
        kwargs = analysis.kwargs
        subject = analysis.subject
        _log.debug(
            f"Evaluating analysis function '{analysis.function.name}' on subject "
            f"'{subject}' with kwargs {kwargs} and storage prefix "
            f"'{analysis.storage_prefix}'..."
        )
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
            f"...done evaluating analysis function '{analysis.function.name}' on "
            f"subject '{subject}'; peak memory usage was {int(peak / 1024 / 1024)} MB."
        )
        save_result(result, Analysis.SUCCESS, peak_memory=peak, dois=dois)
    except Exception as exc:
        _log.warning(f"Exception while performing analysis {analysis_id}: {exc}")
        save_result(
            dict(message=str(exc), traceback=traceback.format_exc()), Analysis.FAILURE
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
            _log.debug(f"Analysis with {analysis_id} does not exist.")
            # Analysis was deleted, e.g. because topography or surface was missing
            pass
    _log.debug(f"Done with task {self.request.id}.")
