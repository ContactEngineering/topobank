import inspect
import logging
import math
import pickle

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q

from guardian.shortcuts import get_users_with_perms

from topobank.analysis.models import Analysis, AnalysisFunction

_log = logging.getLogger(__name__)


def request_analysis(user, analysis_func, subject, *other_args, **kwargs):
    """Request an analysis for a given user.

    :param user: User instance, user who want to see this analysis
    :param subject: instance which will be used as first argument to analysis function
    :param analysis_func: AnalysisFunc instance
    :param other_args: other positional arguments for analysis_func
    :param kwargs: keyword arguments for analysis func
    :returns: Analysis object

    The returned analysis can be a precomputed one or a new analysis is
    submitted may or may not be completed in future. Check database fields
    (e.g. task_state) in order to check for completion.

    The analysis will be marked such that the "users" field points to
    the given user and that there is no other analysis for same function
    and subject that points to that user.
    """

    #
    # Build function signature with current arguments
    #
    subject_type = ContentType.objects.get_for_model(subject)
    pyfunc = analysis_func.python_function(subject_type)

    sig = inspect.signature(pyfunc)

    bound_sig = sig.bind(subject, *other_args, **kwargs)
    bound_sig.apply_defaults()

    pyfunc_kwargs = dict(bound_sig.arguments)

    # subject will always be second positional argument
    # and has an extra column, do not safe reference
    del pyfunc_kwargs[subject_type.model]  # will delete 'topography' or 'surface' or whatever the subject name is

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
        Q(subject_type=subject_type)
        & Q(subject_id=subject.id)
        & Q(function=analysis_func)
        & Q(kwargs=pickled_pyfunc_kwargs)).order_by('start_time').last()  # will be None if not found
    # what if pickle protocol changes? -> No match, old must be sorted out later
    # See also GH 426.

    if analysis is None:
        analysis = submit_analysis(users=[user], analysis_func=analysis_func, subject=subject,
                                   pickled_pyfunc_kwargs=pickled_pyfunc_kwargs)
        _log.info(f"Submitted new analysis for {analysis_func.name} and {subject.name} (user: {user.id})..")
    elif user not in analysis.users.all():
        analysis.users.add(user)
        _log.info("Added user %d to existing analysis %d.", user.id, analysis.id)
    else:
        _log.debug("User %d already registered for analysis %d.", user.id, analysis.id)

    #
    # Retrigger an analysis if there was a failure, maybe sth has been fixed in the meantime
    #
    if analysis.task_state == 'fa':
        new_analysis = submit_analysis(users=analysis.users.all(),
                                       analysis_func=analysis_func, subject=subject,
                                       pickled_pyfunc_kwargs=pickled_pyfunc_kwargs)
        _log.info("Submitted analysis %d again because of failure..", analysis.id)
        analysis.delete()
        analysis = new_analysis

    #
    # Remove user from other analyses with same topography and function
    #
    other_analyses_with_same_user = Analysis.objects.filter(
        ~Q(id=analysis.id)
        & Q(subject_type=subject_type)
        & Q(subject_id=subject.id)
        & Q(function=analysis_func)
        & Q(users__in=[user]))
    for a in other_analyses_with_same_user:
        a.users.remove(user)
        _log.info("Removed user %s from analysis %s with kwargs %s.", user, analysis, pickle.loads(analysis.kwargs))

    return analysis


def renew_analyses_for_subject(subject):
    """Renew all analyses for the given subject.

    At first all existing analyses for the given subject
    will be deleted. Only analyses for the default parameters
    will be automatically generated at the moment.

    Implementation Note:

    This method cannot be easily used in a post_save signal,
    because the pre_delete signal deletes the datafile and
    this also then triggers "renew_analyses".
    """
    from topobank.manager.models import Surface

    analysis_funcs = AnalysisFunction.objects.all()

    # collect users which are allowed to view analyses
    related_surface = subject if isinstance(subject, Surface) else subject.surface
    users = get_users_with_perms(related_surface)

    def submit_all(subj=subject):
        """Trigger analyses for this subject for all available analyses functions."""
        _log.info("Deleting all analyses for %s %d..", subj.get_content_type().name, subj.id)
        subj.analyses.all().delete()
        _log.info("Triggering analyses for %s %d and all analysis functions..", subj.get_content_type().name, subj.id)
        for af in analysis_funcs:
            if af.is_implemented_for_type(subj.get_content_type()):
                try:
                    submit_analysis(users, af, subject=subj)
                except Exception as err:
                    _log.error("Cannot submit analysis for function '%s' and subject '%s' (%s, %d). Reason: %s",
                               af.name, subj, subj.get_content_type().name, subj.id, str(err))

    transaction.on_commit(lambda: submit_all(subject))


def renew_analysis(analysis, use_default_kwargs=False):
    """Delete existing analysis and recreate and submit with same arguments and users.

    Parameters
    ----------
    analysis: Analysis
        Analysis instance to be renewed.
    use_default_kwargs: boolean
        If True, use default arguments of the corresponding analysis function implementation.
        If False (default), use the keyword arguments of the given analysis.

    Returns
    -------
    New analysis object.
    """
    users = analysis.users.all()
    func = analysis.function

    subject_type = ContentType.objects.get_for_model(analysis.subject)

    if use_default_kwargs:
        pickled_pyfunc_kwargs = pickle.dumps(func.get_default_kwargs(subject_type=subject_type))
    else:
        pickled_pyfunc_kwargs = analysis.kwargs

    _log.info("Renewing analysis %d for %d users, function %s, subject type %s, subject id %d .. kwargs: %s",
              analysis.id, len(users), func.name, subject_type, analysis.subject.id,
              pickle.loads(pickled_pyfunc_kwargs))
    analysis.delete()
    return submit_analysis(users, func, subject=analysis.subject,
                           pickled_pyfunc_kwargs=pickled_pyfunc_kwargs)


def submit_analysis(users, analysis_func, subject, pickled_pyfunc_kwargs=None):
    """Create an analysis entry and submit a task to the task queue.

    :param users: sequence of User instances; users which should see the analysis
    :param subject: instance which will be subject of the analysis (first argument of analysis function)
    :param analysis_func: AnalysisFunc instance
    :param pickled_pyfunc_kwargs: pickled kwargs for function which should be saved to database
    :returns: Analysis object

    If None is given for 'pickled_pyfunc_kwargs', the default arguments for the given analysis function are used.
    The default arguments are the ones used in the function implementation (python function).

    Typical instances as subjects are topographies or surfaces.
    """
    subject_type = ContentType.objects.get_for_model(subject)

    #
    # create entry in Analysis table
    #
    if pickled_pyfunc_kwargs is None:
        # Instead of an empty dict, we explicitly store the current default arguments of the analysis function
        pickled_pyfunc_kwargs = pickle.dumps(analysis_func.get_default_kwargs(subject_type=subject_type))

    analysis = Analysis.objects.create(
        subject=subject,
        function=analysis_func,
        task_state=Analysis.PENDING,
        kwargs=pickled_pyfunc_kwargs)

    analysis.users.set(users)

    #
    # delete all completed old analyses for same function and subject and arguments
    # There should be only one analysis per function, subject and arguments
    #
    Analysis.objects.filter(
        ~Q(id=analysis.id)
        & Q(subject_type=subject_type)
        & Q(subject_id=subject.id)
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
    from topobank.taskapp.tasks import perform_analysis
    transaction.on_commit(lambda: perform_analysis.delay(analysis.id))

    return analysis


def get_latest_analyses(user, func, subjects):
    """Get the latest analyses for given function and topographies and user.

    :param user: user which views the analyses
    :param func: AnalysisFunction instance
    :param subjects: iterable of analysis subjects
    :return: Queryset of analyses

    The returned queryset comprises only the latest analyses,
    so for each subject there should be at most one result.
    Only analyses for the given function are returned.

    It is not guaranteed that there are results
    for the returned analyses, even if these analyses are marked as
    successful.
    """

    # FIXME: The query for analyses results should include the parameters

    # Create query from subjects
    query = None
    for subject in subjects:
        ct = ContentType.objects.get_for_model(subject)
        q = Q(subject_type_id=ct.id) & Q(subject_id=subject.id)
        if query is None:
            query = q
        else:
            query = query | q

    if query is None:
        return Analysis.objects.none()

    analyses = Analysis.objects.filter(Q(users__in=[user]) & Q(function=func) & query)

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

def round_to_significant_digits(x, num_dig_digits):
    """Round given number to given number of significant digits

    Parameters
    ----------
    x: flost
        Number to be rounded
    num_dig_digits: int
        Number of significant digits


    Returns
    -------
    Rounded number.

    For NaN, NaN is returned.
    """
    if math.isnan(x):
        return x
    try:
        return round(x, num_dig_digits - int(math.floor(math.log10(abs(x)))) - 1)
    except ValueError:
        return x


