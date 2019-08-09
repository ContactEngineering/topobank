import pickle
import traceback
import inspect

from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from django.conf import settings

from celery_progress.backend import ProgressRecorder

from PyCo.System.Systems import IncompatibleFormulationError

from .celery import app
from .utils import get_package_version_instance

from topobank.analysis.models import Analysis, Configuration
from topobank.manager.models import Topography
from topobank.analysis.functions import IncompatibleTopographyException

EXCEPTION_CLASSES_FOR_INCOMPATIBILITIES = (IncompatibleTopographyException, IncompatibleFormulationError)

def submit_analysis(analysis_func, topography, *other_args, **kwargs):
    """Create an analysis entry and submit a task to the task queue.

    :param topography: Topography instance which will be used to extract first argument to analysis function
    :param analysis_func: AnalysisFunc instance
    :param other_args: other positional arguments for analysis_func
    :param kwargs: keyword arguments for analysis func
    """

    #
    # Build function signature with current arguments
    #
    pyfunc = analysis_func.python_function

    sig = inspect.signature(pyfunc)

    bound_sig = sig.bind(topography, *other_args, **kwargs)
    bound_sig.apply_defaults()

    pyfunc_kwargs = dict(bound_sig.arguments)

    # topography will always be second positional argument
    # and has an extra column, do not safe reference
    del pyfunc_kwargs['topography']

    # progress recorder should also not be saved:
    if 'progress_recorder' in pyfunc_kwargs:
        del pyfunc_kwargs['progress_recorder']

    # same for storage prefix
    if 'storage_prefix' in pyfunc_kwargs:
        del pyfunc_kwargs['storage_prefix']

    #
    # create entry in Analysis table
    #
    analysis = Analysis.objects.create(
        topography=topography,
        function=analysis_func,
        task_state=Analysis.PENDING,
        kwargs=pickle.dumps(pyfunc_kwargs))

    #
    # delete all completed old analyses for same function and topography
    #
    Analysis.objects.filter(
        ~Q(id=analysis.id)
        & Q(topography=topography)
        & Q(function=analysis_func)
        & Q(task_state__in=[Analysis.FAILURE, Analysis.SUCCESS])).delete()

    #
    # TODO delete all started old analyses, where the task does not exist any more
    #
    #maybe_aborted_analyses = Analysis.objects.filter(
    #    ~Q(id=analysis.id)
    #    & Q(topography=topography)
    #    & Q(function=analysis_func)
    #    & Q(task_state__in=[Analysis.STARTED]))
    # How to find out if task is still running?
    #
    #for a in maybe_aborted_analyses:
    #    result = app.AsyncResult(a.task_id)


    #
    # Send task to the queue
    #
    transaction.on_commit(lambda : perform_analysis.delay(analysis.id))




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



