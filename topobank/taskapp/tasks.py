"""
Definition of celery tasks used in TopoBank.
"""

import pickle
import traceback

from django.utils import timezone
from django.db.utils import IntegrityError
from django.conf import settings
from django.shortcuts import reverse

from celery_progress.backend import ProgressRecorder
from celery.signals import after_setup_task_logger
from celery.app.log import TaskFormatter
from celery.utils.log import get_task_logger
from celery import group

from notifications.signals import notify

from SurfaceTopography.Exceptions import CannotPerformAnalysisError
from SurfaceTopography.Support import doi
from ContactMechanics.Systems import IncompatibleFormulationError

from .celeryapp import app
from .utils import get_package_version_instance

from topobank.analysis.functions import IncompatibleTopographyException
from topobank.analysis.models import Analysis, Configuration, AnalysisCollection, RESULT_FILE_BASENAME
from topobank.manager.models import Topography, Surface
from ..utils import store_split_dict
from topobank.users.models import User
from topobank.usage_stats.utils import increase_statistics_by_date, increase_statistics_by_date_and_object, \
    current_statistics

EXCEPTION_CLASSES_FOR_INCOMPATIBILITIES = (IncompatibleTopographyException, IncompatibleFormulationError,
                                           CannotPerformAnalysisError)

_log = get_task_logger(__name__)


@after_setup_task_logger.connect
def setup_task_logger(logger, *args, **kwargs):
    fmt = '%(asctime)s - %(task_id)s - %(task_name)s - %(name)s - %(levelname)s - %(message)s'
    for handler in logger.handlers:
        handler.setFormatter(TaskFormatter(fmt))


def current_configuration():
    """Determine current configuration (package versions) and create appropriate database entries.

    The configuration is needed in order to track down analysis results
    to specific module and package versions. Like this it is possible to
    find all analyses which have been calculated with buggy packages.

    :return: Configuration instance which can be used for analyses
    """
    versions = [get_package_version_instance(pkg_name, version_expr)
                for pkg_name, version_expr in settings.TRACKED_DEPENDENCIES]

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

    def save_result(result, task_state, dois=[]):
        _log.debug(f"Saving result of analysis {analysis_id} to storage...")
        analysis.task_state = task_state
        #default_storage_replace(f'{analysis.storage_prefix}/result.json',
        #                        io.BytesIO(json.dumps(result, cls=NumpyEncoder).encode('utf-8')))
        store_split_dict(analysis.storage_prefix, RESULT_FILE_BASENAME, result)
        #analysis.result = pickle.dumps(result)  # can also be an exception in case of errors!
        analysis.end_time = timezone.now()  # with timezone
        if 'effective_kwargs' in result:
            analysis.kwargs = pickle.dumps(result['effective_kwargs'])
        analysis.dois = list(dois)  # dois is a set, we need to convert it
        analysis.save()
        _log.debug("Done saving analysis result.")

    @doi()
    def evaluate_function(subject, **kwargs):
        return analysis.function.eval(subject, **kwargs)

    #
    # actually perform analysis
    #
    try:
        # noinspection PickleLoad
        kwargs = pickle.loads(analysis.kwargs)
        subject = analysis.subject
        kwargs['progress_recorder'] = progress_recorder
        kwargs['storage_prefix'] = analysis.storage_prefix
        # also request citation information
        dois = set()
        kwargs['dois'] = dois
        _log.debug("Evaluating analysis function '%s' on subject '%s' with kwargs %s and storage prefix '%s'...",
                   analysis.function.name, subject, kwargs, analysis.storage_prefix)
        result = evaluate_function(subject, **kwargs)
        save_result(result, Analysis.SUCCESS, dois)
    except (Topography.DoesNotExist, Surface.DoesNotExist, IntegrityError) as exc:
        _log.warning("Subject for analysis %s doesn't exist any more, so that analysis will be deleted...",
                     analysis.id)
        analysis.delete()
        # we want a real exception here so celery's flower can show the task as failure
        raise
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

            td = analysis.end_time - analysis.start_time
            increase_statistics_by_date(metric=Metric.objects.TOTAL_ANALYSIS_CPU_MS,
                                        increment=1000 * td.total_seconds())
            increase_statistics_by_date_and_object(
                metric=Metric.objects.TOTAL_ANALYSIS_CPU_MS,
                obj=analysis.function,
                increment=1000 * td.total_seconds())

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
def save_landing_page_statistics():
    from trackstats.models import Metric, Period, StatisticByDate
    _log.debug("Saving landing page statistics..")
    #
    # Number of users
    #
    from django.db.models import Q
    from guardian.compat import get_user_model as guardian_user_model
    anon = guardian_user_model().get_anonymous()
    num_users = User.objects.filter(Q(is_active=True) & ~Q(pk=anon.pk)).count()

    StatisticByDate.objects.record(
        metric=Metric.objects.USER_COUNT,
        value=num_users,
        period=Period.DAY
    )

    #
    # Number of surfaces, topographies, analyses
    #
    # Publications should not increase these numbers
    #
    current_stats = current_statistics()

    StatisticByDate.objects.record(
        metric=Metric.objects.SURFACE_COUNT,
        value=current_stats['num_surfaces_excluding_publications'],
        period=Period.DAY
    )
    StatisticByDate.objects.record(
        metric=Metric.objects.TOPOGRAPHY_COUNT,
        value=current_stats['num_topographies_excluding_publications'],
        period=Period.DAY
    )
    StatisticByDate.objects.record(
        metric=Metric.objects.ANALYSIS_COUNT,
        value=current_stats['num_analyses_excluding_publications'],
        period=Period.DAY
    )


@app.task
def renew_squeezed_datafile(topography_id):
    """Renew squeezed datafile for given topography,

    Parameters
    ----------
    topography_id: int
        ID if topography for which the datafile should be calculated
        and saved.

    Returns
    -------
    None
    """
    _log.debug(f"Renewing squeezed datafile for topography id {topography_id}..")
    try:
        topography = Topography.objects.get(id=topography_id)
        topography.renew_squeezed_datafile()
    except Topography.DoesNotExist:
        _log.error(f"Couldn't find topography with id {topography_id}. Cannot renew squeezed datafile.")
    _log.debug(f"Done - renewed squeezed datafile for topography id {topography_id}.")


@app.task
def renew_bandwidth_cache(topography_id):
    """Renew bandwidth cache for given topography,

    Parameters
    ----------
    topography_id: int
        ID if topography for which the datafile should be calculated
        and saved.

    Returns
    -------
    None
    """
    _log.debug(f"Renewing bandwidth cache for topography id {topography_id}..")
    try:
        topography = Topography.objects.get(id=topography_id)
        topography.renew_bandwidth_cache()
    except Topography.DoesNotExist:
        _log.error(f"Couldn't find topography with id {topography_id}. Cannot renew bandwidth cache.")
    _log.debug(f"Done - renewed bandwidth cache for topography id {topography_id}.")


@app.task
def renew_topography_images(topography_id):
    """Renew thumbnail for given topography,

    Parameters
    ----------
    topography_id: int
        ID if topography for which the thumbnail should be generated
        and saved.

    Returns
    -------
    None
    """
    _log.debug(f"Renewing images for topography id {topography_id}..")
    group(renew_topography_thumbnail.si(topography_id),
          renew_topography_dzi.si(topography_id)).delay()
    _log.debug(f"Done - renewed images for topography id {topography_id}.")


@app.task
def renew_topography_thumbnail(topography_id):
    """Renew thumbnail for given topography.

    Parameters
    ----------
    topography_id: int
        ID if topography for which a thumbnail should be generated
        and saved.

    Returns
    -------
    None
    """
    _log.debug(f"Renewing thumbnail for topography id {topography_id}..")
    try:
        topography = Topography.objects.get(id=topography_id)
        topography.renew_thumbnail(none_on_error=False)
    except Topography.DoesNotExist:
        _log.error(f"Couldn't find topography with id {topography_id}. Cannot renew thumbnail.")
    _log.debug(f"Done - renewed thumbnail for topography id {topography_id}.")


@app.task
def renew_topography_dzi(topography_id):
    """Renew DZI files for given topography.

    Parameters
    ----------
    topography_id: int
        ID if topography for which the DZI files should be generated
        and saved.

    Returns
    -------
    None
    """
    _log.debug(f"Renewing DZI images for topography id {topography_id}..")
    try:
        topography = Topography.objects.get(id=topography_id)
        topography.renew_dzi(none_on_error=False)
    except Topography.DoesNotExist:
        _log.error(f"Couldn't find topography with id {topography_id}. Cannot renew DZI.")
    _log.debug(f"Done - renewed DZI for topography id {topography_id}.")


@app.task
def renew_analyses_related_to_topography(topography_id, include_surface=True):
    """Renew analyses related to given topography.

        Parameters
        ----------
        topography_id: int
            ID of topography for which analyses should be regenerated.
        include_surface: bool
            If True, also analyses for the topography's surface are
            regenerated.

        Returns
        -------
        None
    """
    _log.debug(f"Renewing all analyses which are related to topography id {topography_id}..")
    try:
        topography = Topography.objects.get(id=topography_id)
        topography.renew_analyses()
        if include_surface:
            topography.surface.renew_analyses(include_topographies=False)
    except Topography.DoesNotExist:
        _log.error(f"Couldn't find topography with id {topography_id}. Cannot renew analyses.")
