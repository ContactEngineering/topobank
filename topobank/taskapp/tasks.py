import pickle
import traceback

from .celery import app
from topobank.analysis.models import Analysis
from topobank.manager.models import Topography
import topobank.analysis.functions # so functions can be found by eval

def submit_analysis(analysis_func, topography, *other_args, **kwargs):
    """Create an analysis entry and submit a task to the task queue.

    :param topography: Topography instance which will be used to extract first argument to analysis function
    :param analysis_func: AnalysisFunc instance
    :param other_args: other positional arguments for analysis_func
    :param kwargs: keyword arguments for analysis func
    """
    #
    # create entry in Analysis table
    #
    analysis = Analysis.objects.create(
        topography=topography,
        function=analysis_func,
        task_state=Analysis.PENDING,
        args=pickle.dumps(other_args),
        kwargs=pickle.dumps(kwargs))

    #
    # Send task to the queue
    #
    perform_analysis.delay(analysis.id)

@app.task(bind=True, ignore_result=True)
def perform_analysis(self, analysis_id):
    """Perform an analysis which is already present in the database.

    :param self: Celery task on execution (because of bind=True)
    :param analysis_id: ID of Analysis entry in database
    """
    #
    # update entry in Analysis table
    #
    analysis = Analysis.objects.get(id=analysis_id)
    analysis.task_state = Analysis.STARTED
    analysis.task_id = self.request.id
    analysis.save()

    #
    # actually perform analysis
    #

    try:
        other_args = pickle.loads(analysis.args)
        kwargs = pickle.loads(analysis.kwargs)
        compute_func = eval('topobank.analysis.functions.'+analysis.function.pyfunc)
        topography = Topography.objects.get(id=analysis.topography_id).topography()
        result = compute_func(topography, *other_args, **kwargs)
        analysis.task_state = Analysis.SUCCESS
    except Exception as exc:
        analysis.task_state = Analysis.FAILURE
        # TODO add logging
        result = dict(error=traceback.format_exc())

    #
    # update entry with result
    #
    analysis.result = pickle.dumps(result) # can also be an exception in case of errors!
    analysis.save()

