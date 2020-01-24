import pickle
import traceback

from django.utils import timezone
from django.conf import settings
from django.shortcuts import reverse

from celery_progress.backend import ProgressRecorder

from notifications.signals import notify

from PyCo.System.Systems import IncompatibleFormulationError

from .celery import app
from .utils import get_package_version_instance

from topobank.analysis.models import Analysis, Configuration, AnalysisCollection
from topobank.manager.models import Topography, Surface
from topobank.users.models import User
from topobank.analysis.functions import IncompatibleTopographyException
from topobank.usage_stats.utils import increase_statistics_by_date, increase_statistics_by_date_and_object



EXCEPTION_CLASSES_FOR_INCOMPATIBILITIES = (IncompatibleTopographyException, IncompatibleFormulationError)

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

    progress_recorder = ProgressRecorder(self)

    #
    # update entry in Analysis table
    #
    analysis = Analysis.objects.get(id=analysis_id)

    analysis.task_state = Analysis.STARTED
    analysis.task_id = self.request.id
    analysis.start_time = timezone.now() # with timezone
    analysis.configuration = current_configuration()
    analysis.save()

    def save_result(result, task_state):
        analysis.task_state = task_state
        analysis.result = pickle.dumps(result)  # can also be an exception in case of errors!
        analysis.end_time = timezone.now()  # with timezone
        analysis.save()

    #
    # actually perform analysis
    #
    try:
        kwargs = pickle.loads(analysis.kwargs)
        topography = Topography.objects.get(id=analysis.topography_id).topography()
        kwargs['progress_recorder'] = progress_recorder
        kwargs['storage_prefix'] = analysis.storage_prefix
        result = analysis.function.eval(topography, **kwargs)
        save_result(result, Analysis.SUCCESS)
    except Exception as exc:
        is_incompatible = isinstance(exc, EXCEPTION_CLASSES_FOR_INCOMPATIBILITIES)
        save_result(dict(message=str(exc),
                         traceback=traceback.format_exc(),
                         is_incompatible=is_incompatible),
                    Analysis.FAILURE)
        # we want a real exception here so celery's flower can show the task as failure
        raise
    finally:
        #
        # Check whether sth. is to be done because this analysis is part of a collection
        #
        for coll in analysis.analysiscollection_set.all():
            check_analysis_collection.delay(coll.id)

        #
        # Add up number of seconds for CPU time
        #
        analysis = Analysis.objects.get(id=analysis_id)
        td = analysis.end_time-analysis.start_time
        increase_statistics_by_date(metric=Metric.objects.TOTAL_ANALYSIS_CPU_MS,
                                    increment=1000*td.total_seconds())
        increase_statistics_by_date_and_object(
                                    metric=Metric.objects.TOTAL_ANALYSIS_CPU_MS,
                                    obj=analysis.function,
                                    increment=1000 * td.total_seconds())


@app.task
def check_analysis_collection(collection_id):
    """Perform checks on analysis collection. Send notification if needed.

    :param collection_id: id of an AnalysisCollection instance
    :return:
    """

    collection = AnalysisCollection.objects.get(id=collection_id)

    analyses = collection.analyses.all()
    task_states = [ analysis.task_state for analysis in analyses ]

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
                        description="Tasks finished: "+collection.name,
                        href=href)

        else:
            collection.combined_task_state = 'st'

        collection.save()


@app.task
def save_landing_page_statistics():
    from trackstats.models import Metric, Period, StatisticByDate

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
    StatisticByDate.objects.record(
        metric=Metric.objects.SURFACE_COUNT,
        value=Surface.objects.filter().count(),
        period=Period.DAY
    )
    StatisticByDate.objects.record(
        metric=Metric.objects.TOPOGRAPHY_COUNT,
        value=Topography.objects.filter().count(),
        period=Period.DAY
    )
    StatisticByDate.objects.record(
        metric=Metric.objects.ANALYSIS_COUNT,
        value=Analysis.objects.filter().count(),
        period=Period.DAY
    )
