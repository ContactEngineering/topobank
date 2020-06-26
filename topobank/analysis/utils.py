from django.db.models import OuterRef, Subquery
from django.db import transaction
from django.db.models import Q
import inspect
import pickle
import logging

from topobank.analysis.models import Analysis
from topobank.taskapp.tasks import perform_analysis

_log = logging.getLogger(__name__)

def request_analysis(user, analysis_func, topography, *other_args, **kwargs):
    """Request an analysis for a given user.

    :param user: User instance, user who want to see this analysis
    :param topography: Topography instance which will be used to extract first argument to analysis function
    :param analysis_func: AnalysisFunc instance
    :param other_args: other positional arguments for analysis_func
    :param kwargs: keyword arguments for analysis func
    :returns: Analysis object

    The returned analysis can be a precomputed one or a new analysis is
    submitted may or may not be completed in future. Check database fields
    (e.g. task_state) in order to check for completion.

    The analysis will be marked such that the "users" field points to
    the given user and that there is no other analysis for same function
    and topography that points to that user.
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
    # Search for analyses with same topography, function and (pickled) function args
    #
    pickled_pyfunc_kwargs = pickle.dumps(pyfunc_kwargs)
    analysis = Analysis.objects.filter(\
        Q(topography=topography)
        & Q(function=analysis_func)
        & Q(kwargs=pickled_pyfunc_kwargs)).order_by('start_time').last() # will be None if not found
    # what if pickle protocol changes? -> No match, old must be sorted out later
    # See also GH 426.

    if analysis is None:
        analysis = submit_analysis(users=[user], analysis_func=analysis_func, topography=topography,
                                   pickled_pyfunc_kwargs=pickled_pyfunc_kwargs)
        _log.info("Submitted new analysis..")
    elif user not in analysis.users.all():
        analysis.users.add(user)
        _log.info("Added user %d to existing analysis %d.", user.id, analysis.id)
    else:
        _log.info("User %d already registered for analysis %d.", user.id, analysis.id)

    #
    # Retrigger an analysis if there was a failure, maybe sth has been fixed in the meantime
    #
    if analysis.task_state == 'fa':
        new_analysis = submit_analysis(users=analysis.users.all(), analysis_func=analysis_func, topography=topography,
                                   pickled_pyfunc_kwargs=pickled_pyfunc_kwargs)
        _log.info("Submitted analysis %d again because of failure..", analysis.id)
        analysis.delete()
        analysis = new_analysis

    #
    # Remove user from other analyses with same topography and function
    #
    other_analyses_with_same_user = Analysis.objects.filter(
        ~Q(id=analysis.id) \
        & Q(topography=topography) \
        & Q(function=analysis_func) \
        & Q(users__in=[user]))
    for a in other_analyses_with_same_user:
        a.users.remove(user)
        _log.info("Removed user %s from analysis %s with kwargs %s.", user, analysis, pickle.loads(analysis.kwargs))

    return analysis


def renew_analysis(analysis, use_default_kwargs=False):
    """Delete existing analysis and recreate and submit with some arguments and users.

    Parameters
    ----------
    analysis

    Returns
    -------
    New analysis object.

    """
    users = analysis.users.all()
    func = analysis.function
    topography = analysis.topography
    if use_default_kwargs:
        pickled_pyfunc_kwargs = pickle.dumps(func.get_default_kwargs())
    else:
        pickled_pyfunc_kwargs = analysis.kwargs

    _log.info("Renewing analysis %d for %d users, function %s, topography %d .. kwargs: %s",
              analysis.id, len(users), func.name, topography.id, pickle.loads(pickled_pyfunc_kwargs))
    analysis.delete()
    return submit_analysis(users, func, topography, pickled_pyfunc_kwargs)


def submit_analysis(users, analysis_func, topography, pickled_pyfunc_kwargs=None):
    """Create an analysis entry and submit a task to the task queue.

    :param users: sequence of User instances; users which should see the analysis
    :param topography: Topography instance which will be used to extract first argument to analysis function
    :param analysis_func: AnalysisFunc instance
    :param pickled_pyfunc_kwargs: pickled kwargs for function which should be saved to database
    :returns: Analysis object
    """
    #
    # create entry in Analysis table
    #
    if pickled_pyfunc_kwargs is None:
        # Instead of an empty dict, we explicitly store the current default arguments of the analysis function
        pickled_pyfunc_kwargs = pickle.dumps(analysis_func.get_default_kwargs())

    analysis = Analysis.objects.create(
        topography=topography,
        function=analysis_func,
        task_state=Analysis.PENDING,
        kwargs=pickled_pyfunc_kwargs)

    analysis.users.set(users)

    #
    # delete all completed old analyses for same function and topography and arguments
    # There should be only one analysis per function, topography and arguments
    #
    Analysis.objects.filter(
        ~Q(id=analysis.id)
        & Q(topography=topography)
        & Q(function=analysis_func)
        & Q(kwargs=pickled_pyfunc_kwargs)
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

    # Send task to the queue if the analysis has been created
    transaction.on_commit(lambda : perform_analysis.delay(analysis.id))

    return analysis



def get_latest_analyses(user, function_id, topography_ids):
    """Get latest analyses for given function and topographies and user.

    :param user: user which views the analyses
    :param function_id: id of AnalysisFunction instance
    :param topography_ids: iterable of ids of Topography instances

    :return: Queryset of analyses

    The returned queryset is comprised of only the latest analyses,
    so for each topography id there should be at most one result.
    Only analyses for the given function are returned.
    """

    sq_analyses = Analysis.objects \
                .filter(topography_id__in=topography_ids,
                        function_id=function_id,
                        users__in=[user]) \
                .filter(topography=OuterRef('topography'), function=OuterRef('function'),
                        kwargs=OuterRef('kwargs')) \
                .order_by('-start_time')

    # Use this subquery for finding only latest analyses for each (topography, kwargs) group
    analyses = Analysis.objects \
        .filter(pk=Subquery(sq_analyses.values('pk')[:1])) \
        .order_by('topography__name')

    # thanks to minkwe for the contribution at https://gist.github.com/ryanpitts/1304725
    # maybe be better solved with PostGreSQL and Window functions

    return analyses

def mangle_sheet_name(s: str) -> str:
    """Return a string suitable for a sheet name in Excel/Libre Office.

    :param s: sheet name
    :return: string which should be suitable for sheet names
    """

    replacements = {
        ':': '',
        '[': '(',
        ']': ')',
        '*': '',
        '?': '',
        "'": '"',
        "\\": ""
    }

    for x, y in replacements.items():
        s = s.replace(x, y)

    return s
