import pickle
import traceback
import inspect

from django.utils import timezone

from celery_progress.backend import ProgressRecorder, ConsoleProgressRecorder

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
    # Send task to the queue
    #
    transaction.on_commit(lambda : perform_analysis.delay(analysis.id))

class AnalysisProgressRecorder(ProgressRecorder):
    """Progress recorder taking into account io operations before and after calculation."""

    def __init__(self, task, extra_steps):
        super().__init__(task)
        self._extra_steps = extra_steps

    def _super_set_progress(self, current, total):
        if self.task == perform_analysis: # just in case this is not called with a real task
            print('processed {} items of {}'.format(current, total))
        else:
            super().set_progress(current, total + self._extra_steps)
        #try:
        #    super().set_progress(current, total + self._extra_steps)
        #except Exception:
        #    # as expected, this fails if not a real task is given
        #    pass

    def set_progress(self, current, total):
        return self._super_set_progress(current, total)

    def set_progress_to_complete(self):
        return self._super_set_progress(1,1)

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

    progress_recorder = AnalysisProgressRecorder(self, 3)

    # we add 3 extra steps when creating the progress recorder:
    # - saving new "started" state of analysis object
    # - loading the topography
    # - saving analysis results
    #
    # This means, the function cannot fill the progress bar alone.

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
        result = analysis.function.eval(progress_recorder, topography, **kwargs)
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

    progress_recorder.set_progress_to_complete()

