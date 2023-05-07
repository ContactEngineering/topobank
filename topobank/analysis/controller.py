import inspect
import logging

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q

from ..manager.utils import subjects_from_dict, subjects_to_dict, dict_from_b64, subjects_to_b64

from ..taskapp.tasks import perform_analysis

from .models import Analysis, AnalysisFunction
from .serializers import AnalysisResultSerializer

_log = logging.getLogger(__name__)


# This used only in the `trigger_analyses` management command
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
    analysis_funcs = AnalysisFunction.objects.all()

    # collect users which are allowed to use these analyses by default
    users_for_subject = subject.get_users_with_perms()

    def submit_all(subj=subject):
        """Trigger analyses for this subject for all available analyses functions."""
        _log.info(f"Deleting all analyses for {subj.get_content_type().name} {subj.id}...")
        subj.analyses.all().delete()
        _log.info(f"Triggering analyses for {subj.get_content_type().name} {subj.id} and all analysis functions...")
        for af in analysis_funcs:
            subject_type = subj.get_content_type()
            if af.is_implemented_for_type(subject_type):
                # filter also for users who are allowed to use the function
                users = [u for u in users_for_subject if af.get_implementation(subject_type).is_available_for_user(u)]
                try:
                    submit_analysis(users, af, subject=subj)
                except Exception as err:
                    _log.error(f"Cannot submit analysis for function '{af.name}' and subject '{subj}' "
                               f"({subj.get_content_type().name} {subj.id}). Reason: {str(err)}")

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
        pyfunc_kwargs = func.get_default_kwargs(subject_type=subject_type)
    else:
        pyfunc_kwargs = analysis.kwargs

    _log.info(f"Renewing analysis {analysis.id} for {len(users)} users, function {func.name}, "
              f"subject type {subject_type}, subject id {analysis.subject.id} .. "
              f"kwargs: {pyfunc_kwargs}")
    analysis.delete()
    return submit_analysis(users, func, subject=analysis.subject,
                           pyfunc_kwargs=pyfunc_kwargs)


def submit_analysis(users, analysis_func, subject, pyfunc_kwargs=None):
    """Create an analysis entry and submit a task to the task queue.

    :param users: sequence of User instances; users which should see the analysis
    :param subject: instance which will be subject of the analysis (first argument of analysis function)
    :param analysis_func: AnalysisFunc instance
    :param pyfunc_kwargs: kwargs for function which should be saved to database
    :returns: Analysis object

    If None is given for 'pyfunc_kwargs', the default arguments for the given analysis function are used.
    The default arguments are the ones used in the function implementation (python function).

    Typical instances as subjects are topographies or surfaces.
    """
    subject_type = ContentType.objects.get_for_model(subject)

    #
    # create entry in Analysis table
    #
    if pyfunc_kwargs is None:
        # Instead of an empty dict, we explicitly store the current default arguments of the analysis function
        pyfunc_kwargs = analysis_func.get_default_kwargs(subject_type=subject_type)

    analysis = Analysis.objects.create(
        subject=subject,
        function=analysis_func,
        task_state=Analysis.PENDING,
        kwargs=pyfunc_kwargs)

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
        & Q(kwargs=pyfunc_kwargs)
        & Q(task_state__in=[Analysis.FAILURE, Analysis.SUCCESS])).delete()

    #
    # TODO delete all started old analyses, where the task does not exist any more
    #
    # maybe_aborted_analyses = Analysis.objects.filter(
    #    ~Q(id=analysis.id)
    #    & Q(topography=topography)
    #    & Q(function=analysis_func)
    #    & Q(task_state__in=[Analysis.STARTED]))
    # How to find out if task is still running?
    #
    # for a in maybe_aborted_analyses:
    #    result = app.AsyncResult(a.task_id)

    # Send task to the queue if the analysis has been created
    transaction.on_commit(lambda: perform_analysis.delay(analysis.id))

    return analysis


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
    analysis = Analysis.objects.filter( \
        Q(subject_type=subject_type)
        & Q(subject_id=subject.id)
        & Q(function=analysis_func)
        & Q(kwargs=pyfunc_kwargs)).order_by('start_time').last()  # will be None if not found
    # what if pickle protocol changes? -> No match, old must be sorted out later
    # See also GH 426.

    if analysis is None:
        analysis = submit_analysis(users=[user], analysis_func=analysis_func, subject=subject,
                                   pyfunc_kwargs=pyfunc_kwargs)
        _log.info(f"Submitted new analysis for {analysis_func.name} and {subject.name} (User {user})...")
    elif user not in analysis.users.all():
        analysis.users.add(user)
        _log.info(f"Added user {user} to existing analysis {analysis.id}.")
    else:
        _log.debug(f"User {user} already registered for analysis {analysis.id}.")

    #
    # Retrigger an analysis if there was a failure, maybe sth has been fixed in the meantime
    #
    if analysis.task_state == Analysis.FAILURE:
        new_analysis = submit_analysis(users=analysis.users.all(),
                                       analysis_func=analysis_func, subject=subject,
                                       pyfunc_kwargs=pyfunc_kwargs)
        _log.info(f"Submitted analysis {analysis.id} again because of failure..")
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
        _log.info(f"Removed user {user} from analysis {analysis} with kwargs {analysis.kwargs}.")

    return analysis


class AnalysisController:
    """Retrieve and toggle status of analyses"""

    def __init__(self, user, subjects=None, function=None, function_id=None, function_kwargs=None):
        """
        Construct a controller object that filters for specific user, subjects,
        functions, and function arguments. If a parameter is None, then it
        does not filter for this property (but returns all analyses).

        Parameters
        ----------
        user : topobank.manager.models.User
            Currently logged-in user.
        subjects : list of Topography, Surface or SurfaceCollection, optional
            Subjects for which to filter analyses. (Default: None)
        function : AnalysisFunction, optional
            Analysis function object. (Default: None)
        function_id : int, optional
            id of analysis function. (Default: None)
        """
        self._user = user
        if function is None:
            if function_id is None:
                self._function = None
            else:
                self._function = AnalysisFunction.objects.get(id=function_id)
        elif function_id is None:
            self._function = function
        else:
            raise ValueError('Please provide either `function` or `function_id`, not both')
        self._function_kwargs = function_kwargs

        # Calculate subjects for the analyses, filtered for those which have an implementation
        self._subjects = None if subjects is None else subjects_from_dict(subjects, function=self._function)

        # Find the latest analyses for which the user has read permission for the related data
        self._analyses = self._get_latest_analyses()

        self._reset_cache()

    @staticmethod
    def from_request(request):
        """
        Construct an `AnalysisControlLer` object from a request object.

        Parameters
        ----------
        request : rest_framework.request.Request
            REST request object

        Returns
        controller : AnalysisController
            The analysis controller object
        """
        user = request.user
        data = request.data

        function_id = data.get('function_id')
        if function_id is not None:
            function_id = int(function_id)
        subjects = data.get('subjects')
        if subjects is not None and isinstance(subjects, str):
            subjects = dict_from_b64(subjects)
        function_kwargs = data.get('function_kwargs')
        if function_kwargs is not None and isinstance(function_kwargs, str):
            function_kwargs = dict_from_b64(function_kwargs)

        return AnalysisController(user, subjects=subjects, function_id=function_id, function_kwargs=function_kwargs)

    def _reset_cache(self):
        self._dois = None
        self._unique_kwargs = None
        self._has_nonunique_kwargs = None
        self._subjects_without_analysis_results = None

    @property
    def dois(self):
        if self._dois is None:
            self._dois = self._get_dois()
        return self._dois

    @property
    def unique_kwargs(self):
        if self._unique_kwargs is None:
            self._unique_kwargs, self._has_nonunique_kwargs = self._get_unique_kwargs()
        return self._unique_kwargs

    @property
    def has_nonunique_kwargs(self):
        if self._has_nonunique_kwargs is None:
            self._unique_kwargs, self._has_nonunique_kwargs = self._get_unique_kwargs()
        return self._has_nonunique_kwargs

    @property
    def subjects_without_analysis_results(self):
        if self._subjects_without_analysis_results is None:
            self._subjects_without_analysis_results = self._get_subjects_without_analysis_results()
        return self._subjects_without_analysis_results

    @property
    def function(self):
        return self._function

    @property
    def subjects(self):
        return self._subjects

    @property
    def subjects_dict(self):
        # The following is needed for re-triggering analyses, now filtered
        # in order to trigger only for subjects which have an implementation
        return None if self._subjects is None else subjects_to_dict(self._subjects)

    @property
    def subjects_b64(self):
        # The following is needed for re-triggering analyses, now filtered
        # in order to trigger only for subjects which have an implementation
        return None if self._subjects is None else subjects_to_b64(self._subjects)

    def get(self, task_states=None, has_result_file=None, subject_type=None, subject_id=None):
        """
        Return list of analyses filtered by arguments (if present).

        Parameters
        ----------
        task_states : list of str, optional
            List of task states to filter for, e.g. ['su', 'fa'] to filter for
            success and failure. (Default: None)
        has_result_file : boolean, optional
            If true, only return analyses that have a results file. If false,
            return analyses without a results file. Don't filter for results
            file if unset. (Default: None)
        subject_type : int, optional
            Filter for a specific subject type. (Default: None)
        subject_id : int, optional
            Filter for a specific subject id. (Default: None)
        """
        if task_states is None:
            if has_result_file is None:
                analyses = self._analyses
            else:
                analyses = [analysis for analysis in self._analyses if analysis.has_result_file == has_result_file]
        else:
            if has_result_file is None:
                analyses = [analysis for analysis in self._analyses if analysis.task_state in task_states]
            else:
                analyses = [analysis for analysis in self._analyses if analysis.task_state in task_states and
                            analysis.has_result_file == has_result_file]
        if subject_type is not None:
            analyses = [analysis for analysis in analyses if analysis.subject_type == subject_type]
        if subject_id is not None:
            analyses = [analysis for analysis in analyses if analysis.subject_id == subject_id]
        return analyses

    def __len__(self):
        return len(self._analyses)

    def _get_latest_analyses(self):
        """
        Get the latest analyses.

        The returned queryset comprises only the latest analyses, so for each
        subject there should be at most one result. Only analyses for the
        given function are returned and only analyses which should be visible
        for the given user.

        It is not guaranteed that there are results for the returned analyses
        or if these analyses are marked as successful.
        """
        # Query for user
        query = Q(users=self._user)

        # Add function to query
        if self._function is not None:
            query = Q(function=self._function) & query

        # Add kwargs (if specified)
        if self._function_kwargs is not None:
            query = Q(kwargs=self._function_kwargs) & query

        # Query for subjects
        if self._subjects is not None and len(self._subjects) > 0:
            subjects_query = None
            for subject in self._subjects:
                ct = ContentType.objects.get_for_model(subject)
                q = Q(subject_type_id=ct.id) & Q(subject_id=subject.id)
                subjects_query = q if subjects_query is None else subjects_query | q
            query = subjects_query & query

        # Find analyses
        analyses = Analysis.objects.filter(query) \
            .order_by('subject_type_id', 'subject_id', '-start_time').distinct("subject_type_id", 'subject_id')

        # filter by current visibility for user
        return [analysis for analysis in analyses if analysis.is_visible_for_user(self._user)]

    def _get_subjects_without_analysis_results(self):
        """Find analyses that are missing (i.e. have not yet run)"""
        # collect list of subjects for which an analysis instance is missing
        subjects_with_analysis_results = [analysis.subject for analysis in self._analyses]
        if self._subjects is None:
            # If the no subjects are specified, then there are no subjects without analysis result by definition.
            # This controller is then simply returning the analyses that have run.
            subjects_without_analysis_results = []
        else:
            subjects_without_analysis_results = [subject for subject in self._subjects
                                                 if subject not in subjects_with_analysis_results]

        return subjects_without_analysis_results

    def _get_unique_kwargs(self):
        """
        Collect all keyword arguments and check whether they are equal.
        Returns a dictionary with unique keyword arguments.
        """
        unique_kwargs = None
        has_nonunique_kwargs = False
        for analysis in self._analyses:
            kwargs = analysis.kwargs
            if unique_kwargs is None:
                unique_kwargs = kwargs
            else:
                for key, value in kwargs.items():
                    if key in unique_kwargs:
                        if unique_kwargs[key] != value:
                            # Delete nonunique key
                            del unique_kwargs[key]
                            has_nonunique_kwargs = True
        return {} if unique_kwargs is None else unique_kwargs, has_nonunique_kwargs

    def trigger_missing_analyses(self):
        """
        Automatically trigger analyses for missing subjects (topographies,
        surfaces or surface collections).

        Save keyword arguments which should be used for missing analyses,
        sorted by subject type.
        """

        function_kwargs = self.unique_kwargs
        # Manually provided function kwargs override unique kwargs from prior analysis query
        if self._function_kwargs is not None:
            function_kwargs.update(self._function_kwargs)

        # For every possible implemented subject type the following is done:
        # We use the common unique keyword arguments if there are any; if not
        # the default arguments for the implementation is used

        subjects_triggered = []
        for subject in self.subjects_without_analysis_results:
            if subject.is_shared(self._user):
                triggered_analysis = request_analysis(self._user, self._function, subject, **function_kwargs)
                subjects_triggered += [subject]
                _log.info(f"Triggered analysis {triggered_analysis.id} for function '{self._function.name}' "
                          f"and subject '{subject}'.")

        # Now all subjects which needed to be triggered, should have been triggered with common arguments if possible
        # collect information about available analyses again.
        if len(subjects_triggered) > 0:
            self._analyses = self._get_latest_analyses()
            self._reset_cache()

    def _get_dois(self):
        """Collect dois from all available analyses"""
        return sorted(set().union(*[analysis.dois for analysis in self._analyses]))

    def to_representation(self, task_states=None, has_result_file=None, request=None):
        """
        Return list of serialized analyses filtered by arguments (if present).

        Parameters
        ----------
        task_states : list of str, optional
            List of task states to filter for, e.g. ['su', 'fa'] to filter for
            success and failure. (Default: None)
        has_result_file : boolean, optional
            If true, only return analyses that have a results file. If false,
            return analyses without a results file. Don't filter for results
            file if unset. (Default: None)
        request : Request, optional
            request object (for HyperlinkedRelatedField). (Default: None)
        """
        if request is None:
            context = None
        else:
            context = {'request': request}
        return [AnalysisResultSerializer(analysis, context=context).data for analysis in
                self.get(task_states=task_states, has_result_file=has_result_file)]

    def get_context(self, task_states=None, has_result_file=None, request=None):
        """
        Construct a standardized context dictionary.

        Parameters
        ----------
        task_states : list of str, optional
            List of task states to filter for, e.g. ['su', 'fa'] to filter for
            success and failure. (Default: None)
        has_result_file : boolean, optional
            If true, only return analyses that have a results file. If false,
            return analyses without a results file. Don't filter for results
            file if unset. (Default: None)
        request : Request, optional
            request object (for HyperlinkedRelatedField). (Default: None)
        """
        return {
            'analyses': self.to_representation(task_states=task_states, has_result_file=has_result_file,
                                               request=request),
            'dois': self.dois,
            'functionName': self.function.name,
            'functionId': self.function.id,
            'subjects': self.subjects_dict,  # can be used to re-trigger analyses
            'uniqueKwargs': self.unique_kwargs,
            'hasNonuniqueKwargs': self.has_nonunique_kwargs
        }
