import logging
import traceback
import tracemalloc

import numpy as np
from ContactMechanics.Systems import IncompatibleFormulationError
from django.conf import settings
from django.db.models import Case, F, Max, When
from django.shortcuts import reverse
from django.utils import timezone
from notifications.signals import notify
from SurfaceTopography.Exceptions import CannotPerformAnalysisError
from SurfaceTopography.Support import doi

from ..taskapp.celeryapp import app
from ..taskapp.tasks import ProgressRecorder
from ..taskapp.utils import get_package_version
from ..usage_stats.utils import increase_statistics_by_date, increase_statistics_by_date_and_object
from ..utils import store_split_dict
from .functions import IncompatibleTopographyException
from .models import RESULT_FILE_BASENAME, Analysis, AnalysisCollection, AnalysisFunction, Configuration

EXCEPTION_CLASSES_FOR_INCOMPATIBILITIES = (IncompatibleTopographyException, IncompatibleFormulationError,
                                           CannotPerformAnalysisError)

_log = logging.getLogger(__name__)


def current_configuration():
    """Determine current configuration (package versions) and create appropriate database entries.

    The configuration is needed in order to track down analysis results
    to specific module and package versions. Like this it is possible to
    find all analyses which have been calculated with buggy packages.

    :return: Configuration instance which can be used for analyses
    """
    versions = [get_package_version(pkg_name, version_expr)
                for pkg_name, version_expr, license, homepage in settings.TRACKED_DEPENDENCIES]

    def make_config_from_versions():
        c = Configuration.objects.create()
        c.versions.set(versions)
        return c

    if Configuration.objects.count() == 0:
        return make_config_from_versions()

    #
    # Find out whether the latest configuration has exactly these versions
    #
    latest_config = Configuration.objects.latest('valid_since')

    current_version_ids = set(v.id for v in versions)
    latest_version_ids = set(v.id for v in latest_config.versions.all())

    if current_version_ids == latest_version_ids:
        return latest_config
    else:
        return make_config_from_versions()


@app.task(bind=True)
def perform_analysis(self, analysis_id):
    """Perform an analysis which is already present in the database.

    :param self: Celery task on execution (because of bind=True)
    :param analysis_id: ID of Analysis entry in database

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
            _log.debug(f"Saving result of analysis {analysis_id} with task state '{task_state}' and peak memory usage "
                       f"of {int(peak_memory / 1024 / 1024)} MB to storage...")
        else:
            _log.debug(f"Saving result of analysis {analysis_id} with task state '{task_state}'...")
        analysis.task_state = task_state
        store_split_dict(analysis.storage_prefix, RESULT_FILE_BASENAME, result)
        analysis.end_time = timezone.now()  # with timezone
        analysis.task_memory = peak_memory
        analysis.dois = list(dois)  # dois is a set, we need to convert it
        analysis.save()

    @doi()
    def evaluate_function(subject, **kwargs):
        return analysis.function.eval(subject, **kwargs)

    #
    # actually perform analysis
    #
    try:
        kwargs = analysis.kwargs
        subject = analysis.subject
        _log.debug(f"Evaluating analysis function '{analysis.function.name}' on subject '{subject}' with "
                   f"kwargs {kwargs} and storage prefix '{analysis.storage_prefix}'...")
        # also request citation information
        dois = set()
        tracemalloc.start()
        tracemalloc.reset_peak()
        result = evaluate_function(subject, progress_recorder=progress_recorder, storage_prefix=analysis.storage_prefix,
                                   dois=dois, **kwargs)
        size, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        _log.debug(f"...done evaluating analysis function '{analysis.function.name}' on subject '{subject}'; peak "
                   f"memory usage was {int(peak / 1024 / 1024)} MB.")
        save_result(result, Analysis.SUCCESS, peak_memory=peak, dois=dois)
    except Exception as exc:
        is_incompatible = isinstance(exc, EXCEPTION_CLASSES_FOR_INCOMPATIBILITIES)
        _log.warning(f"Exception while performing analysis {analysis_id} (compatible? {is_incompatible}): {exc}")
        save_result(dict(message=str(exc),
                         traceback=traceback.format_exc(),
                         is_incompatible=is_incompatible),
                    Analysis.FAILURE)
        # we want a real exception here so celery's flower can show the task as failure
        raise
    finally:
        try:
            #
            # first check whether analysis is still there
            #
            analysis = Analysis.objects.get(id=analysis_id)

            #
            # Check whether sth. is to be done because this analysis is part of a collection
            #
            for coll in analysis.analysiscollection_set.all():
                check_analysis_collection.delay(coll.id)

            #
            # Add up number of seconds for CPU time
            #
            from trackstats.models import Metric

            td = analysis.duration
            if td is not None:
                increase_statistics_by_date(metric=Metric.objects.TOTAL_ANALYSIS_CPU_MS,
                                            increment=1000 * td.total_seconds())
                increase_statistics_by_date_and_object(
                    metric=Metric.objects.TOTAL_ANALYSIS_CPU_MS,
                    obj=analysis.function,
                    increment=1000 * td.total_seconds())
            else:
                _log.warning(f'Duration for analysis with {analysis_id} could not be computed.')

        except Analysis.DoesNotExist:
            _log.debug(f"Analysis with {analysis_id} does not exist.")
            # Analysis was deleted, e.g. because topography or surface was missing
            pass
    _log.debug(f"Done with task {self.request.id}.")


@app.task
def check_analysis_collection(collection_id):
    """Perform checks on analysis collection. Send notification if needed.

    :param collection_id: id of an AnalysisCollection instance
    :return:
    """

    collection = AnalysisCollection.objects.get(id=collection_id)

    analyses = collection.analyses.all()
    task_states = [analysis.task_state for analysis in analyses]

    has_started = any(ts not in ['pe'] for ts in task_states)
    has_failure = any(ts in ['fa'] for ts in task_states)
    is_done = all(ts in ['fa', 'su'] for ts in task_states)

    if has_started:
        if is_done:
            #
            # Notify owner of the collection
            #
            collection.combined_task_state = 'fa' if has_failure else 'su'

            href = reverse('analysis:collection', kwargs=dict(collection_id=collection.id))

            notify.send(sender=collection, recipient=collection.owner, verb="finished",
                        description="Tasks finished: " + collection.name,
                        href=href)

        else:
            collection.combined_task_state = 'st'

        collection.save()


@app.task
def fit_memory_model():
    """Fit a simple model for predicting memory usage of an analysis task."""
    max_nb_data_pts = Case(When(subject_dispatch__surface__isnull=False,
                                then=Max(
                                    F('subject_dispatch__surface__topography__resolution_x') * Case(
                                        When(
                                            subject_dispatch__surface__topography__resolution_y__isnull=False,
                                            then=F(
                                                'subject_dispatch__surface__topography__resolution_y')),
                                        default=1))),
                           default=F('subject_dispatch__topography__resolution_x') * Case(
                               When(subject_dispatch__topography__resolution_y__isnull=False,
                                    then=F('subject_dispatch__topography__resolution_y')),
                               default=1))
    for function in AnalysisFunction.objects.all():
        if Analysis.objects.filter(function=function).count() > 0:
            y, x = np.transpose([
                list(analysis.values()) for analysis in
                Analysis.objects.filter(function=function).values('task_memory').annotate(
                    max_nb_data_pts=max_nb_data_pts)
            ])
            print(x, y)
            function.memory_slope, function.memory_offset = np.polyfit(x, y, 1)
            function.save()
