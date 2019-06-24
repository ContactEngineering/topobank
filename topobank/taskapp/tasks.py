import pickle
import traceback
import inspect

from django.utils import timezone
from django.db import transaction
from django.db.models import Q

from celery_progress.backend import ProgressRecorder

from .celery import app
from topobank.analysis.models import Analysis
from topobank.manager.models import Topography


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

    # progress recorder should also not be saved, will always be first argument:
    if 'progress_recorder' in pyfunc_kwargs:
        del pyfunc_kwargs['progress_recorder']

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
    # Send task to the queue
    #
    transaction.on_commit(lambda : perform_analysis.delay(analysis.id))


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

    """

    progress_recorder = ProgressRecorder(self)

    #
    # update entry in Analysis table
    #
    analysis = Analysis.objects.get(id=analysis_id)
    analysis.task_state = Analysis.STARTED
    analysis.task_id = self.request.id
    analysis.start_time = timezone.now() # with timezone
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
        result = analysis.function.eval(topography, **kwargs)
        save_result(result, Analysis.SUCCESS)
    except Exception as exc:
        save_result(dict(error=traceback.format_exc()), Analysis.FAILURE)
        # we want a real exception here so flower can show the task as failure
        raise



