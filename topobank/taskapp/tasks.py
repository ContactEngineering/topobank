import pickle
import traceback
import datetime
import inspect

from django.utils import timezone

from .celery import app
from topobank.analysis.models import Analysis
from topobank.manager.models import Topography
from django.db import transaction

def submit_analysis(analysis_func, topography, *other_args, **kwargs):
    """Create an analysis entry and submit a task to the task queue.

    :param topography: Topography instance which will be used to extract first argument to analysis function
    :param analysis_func: AnalysisFunc instance
    :param other_args: other positional arguments for analysis_func
    :param kwargs: keyword arguments for analysis func
    """

    pyfunc = analysis_func.python_function

    sig = inspect.signature(pyfunc)

    bound_sig = sig.bind(topography, *other_args, **kwargs)
    bound_sig.apply_defaults()

    pyfunc_kwargs = dict(bound_sig.arguments)

    # topography will always be first positional argument
    # and has an extra column, do not safe reference
    del pyfunc_kwargs['topography']

    #
    # create entry in Analysis table
    #
    analysis = Analysis.objects.create(
        topography=topography,
        function=analysis_func,
        task_state=Analysis.PENDING,
        kwargs=pickle.dumps(pyfunc_kwargs))

    #
    # Send task to the queue
    #
    transaction.on_commit(lambda : perform_analysis.delay(analysis.id))

@app.task(bind=True, ignore_result=True)
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
    #
    # update entry in Analysis table
    #
    analysis = Analysis.objects.get(id=analysis_id)
    analysis.task_state = Analysis.STARTED
    analysis.task_id = self.request.id
    analysis.start_time = timezone.now() # with timezone
    analysis.save()

    #
    # actually perform analysis
    #
    try:
        kwargs = pickle.loads(analysis.kwargs)
        topography = Topography.objects.get(id=analysis.topography_id).topography()
        result = analysis.function.eval(topography, **kwargs)
        analysis.task_state = Analysis.SUCCESS
    except Exception as exc:
        analysis.task_state = Analysis.FAILURE
        result = dict(error=traceback.format_exc())

    #
    # update entry with result
    #
    analysis.result = pickle.dumps(result) # can also be an exception in case of errors!
    analysis.end_time = timezone.now() # with timezone
    analysis.save()
