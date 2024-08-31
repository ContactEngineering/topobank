import logging

from django.db import transaction
from django.db.models import Q

from ..manager.utils import (
    dict_from_base64,
    subjects_from_dict,
    subjects_to_base64,
    subjects_to_dict,
)
from .models import Analysis, AnalysisFunction, AnalysisSubject
from .registry import ImplementationMissingAnalysisFunctionException
from .serializers import AnalysisResultSerializer
from .tasks import perform_analysis
from .utils import find_children

_log = logging.getLogger(__name__)


def run_existing_analysis_again(analysis, use_default_kwargs=False):
    """
    Delete existing analysis and recreate and submit with same arguments and user.

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
    user = analysis.user
    func = analysis.function

    if use_default_kwargs:
        kwargs = func.get_default_kwargs()
    else:
        kwargs = analysis.kwargs

    _log.info(
        f"Renewing analysis {analysis.id}: User {user}, function {func.name}, "
        f"subject {analysis.subject}, kwargs: {kwargs}"
    )
    analysis.delete()
    return submit_analysis(
        user, func, subject=analysis.subject, kwargs=kwargs
    )


def submit_analysis(user, func, subject, kwargs=None):
    """
    Create an analysis entry and submit a task to the task queue.

    Parameters
    ----------
    user : topobank.users.models.User
        Users which should see the analysis.
    subject : Tag or Topography or Surface
        Instance which will be subject of the analysis (first argument of
        analysis function).
    func : AnalysisFunction
        The actual analysis function to be executed.
    kwargs : dict, optional
        Keyword arguments for the function which should be saved to database.
        If None is given, the default arguments for the given analysis
        function are used. The default arguments are the ones used in the
        function implementation (python function). (Default: None)

    Returns
    -------
    Analysis object
    """
    # Get default function arguments if none are provided
    if kwargs is None:
        kwargs = func.get_default_kwargs()

    # delete all completed old analyses for same function and subject and arguments
    # There should be only one analysis per function, subject and arguments
    Analysis.objects.filter(
        Q(user=user)
        & AnalysisSubject.Q(subject)
        & Q(function=func)
        & Q(kwargs=kwargs)
        & Q(task_state__in=[Analysis.FAILURE, Analysis.SUCCESS])
    ).delete()

    # Validate kwargs
    func.get_implementation().validate(kwargs)

    # Check if user can actually access the subject
    subject.authorize_user(user, "view")

    # Create new entry in the Analysis table
    analysis = Analysis.objects.create(
        user=user,
        subject_dispatch=AnalysisSubject.create(subject),
        function=func,
        task_state=Analysis.PENDING,
        kwargs=kwargs,
    )

    # Send task to the queue if the analysis has been created
    # Note: on_commit will not execute in tests, unless transaction=True is added to
    # pytest.mark.django_db
    _log.debug(f"Submitting task for analysis {analysis.id}...")
    transaction.on_commit(lambda: perform_analysis.delay(analysis.id))

    return analysis


def submit_analysis_if_missing(
    user, func, subject, kwargs=None, progress_recorder=None, storage_prefix=None
):
    """
    Request an analysis for a given user, which is computed only if it is missing.

    Parameters
    ----------
    user : User
        User instance, user who wants to see this analysis.
    subject : Tag or Surface or Topography
        Instance which will be used as the first argument to the analysis function.
    func : AnalysisFunction
        AnalysisFunc instance.
    kwargs : dict, optional
        Keyword arguments for the analysis function. (Default: None)

    Returns
    -------
    Analysis
        The returned analysis can be a precomputed one or a new analysis is
        submitted that may or may not be completed in the future. Check database fields
        (e.g. task_state) in order to check for completion.

    The analysis will be marked such that the "user" field points to
    the given user and that there is no other analysis for the same function
    and subject that points to that user.
    """
    # Get default function arguments if none are provided
    if kwargs is None:
        kwargs = func.get_default_kwargs()

    # Search for analyses with same user, topography, function and function args
    analysis = (
        Analysis.objects.filter(
            Q(user=user)
            & AnalysisSubject.Q(subject)
            & Q(function=func)
            & Q(kwargs=kwargs)
        )
        .order_by("start_time")
        .last()
    )  # will be None if not found

    if analysis is None:
        analysis = submit_analysis(
            user=user,
            func=func,
            subject=subject,
            kwargs=kwargs,
        )
        _log.info(
            f"Submitted new analysis for {func.name} and {subject.name} "
            f"(User {user})..."
        )
    else:
        _log.debug(f"User {user} already registered for analysis {analysis.id}.")

    #
    # Retrigger an analysis if there was a failure, maybe sth has been fixed in the
    # meantime
    #
    if analysis.task_state == Analysis.FAILURE:
        new_analysis = submit_analysis(
            user=analysis.user,
            func=func,
            subject=subject,
            kwargs=kwargs,
        )
        _log.info(f"Submitted analysis {analysis.id} again because of failure..")
        analysis.delete()
        analysis = new_analysis

    return analysis


class AnalysisController:
    """Retrieve and toggle status of analyses"""

    queryset = Analysis.objects.all().select_related(
        "function",
        "subject_dispatch__tag",
        "subject_dispatch__topography",
        "subject_dispatch__surface",
    )

    def __init__(
        self,
        user,
        subjects=None,
        function=None,
        function_id=None,
        function_kwargs=None,
        with_children=True,
    ):
        """
        Construct a controller object that filters for specific user, subjects,
        functions, and function arguments. If a parameter is None, then it
        does not filter for this property (but returns all analyses).

        Parameters
        ----------
        user : topobank.manager.models.User
            Currently logged-in user.
        subjects : list of Tag, Topography or Surface, optional
            Subjects for which to filter analyses. (Default: None)
        function : AnalysisFunction, optional
            Analysis function object. (Default: None)
        function_id : int, optional
            id of analysis function. (Default: None)
        with_children : bool, optional
            Also return analyses of children, i.e. of topographies that belong
            to a surface. (Default: True)
        """
        self._user = user

        if subjects is None:
            raise ValueError(
                "Please restrict this analysis controller to specific subjects."
            )

        if function is None:
            if function_id is None:
                self._function = None
            else:
                self._function = AnalysisFunction.objects.get(id=function_id)
        elif function_id is None:
            self._function = function
        else:
            raise ValueError(
                "Please provide either `function` or `function_id`, not both."
            )

        if self._function is None:
            raise ValueError(
                "Please restrict this analysis controller to a specific function."
            )

        if not self._function.has_permission(user):
            raise PermissionError(
                f"User {self._user} does not have access to this analysis function."
            )

        self._function_kwargs = function_kwargs

        # Calculate subjects for the analyses, filtered for those which have an
        # implementation
        if isinstance(subjects, dict):
            subjects = subjects_from_dict(subjects)

        # Check permissions
        self._subjects = []
        for subject in subjects:
            try:
                subject.authorize_user(self._user, "view")
                self._subjects += [subject]
            except PermissionError:
                pass

        # Surface permissions are checked in `subjects_from_dict`. Since children (topographies) inherit the permission
        # from their parents, we do not need to do an additional permissions check.
        if with_children:
            self._subjects = find_children(self._subjects)

        # Find the latest analyses for which the user has read permission for the related data
        self._analyses = self._get_latest_analyses()

        self._reset_cache()

    @staticmethod
    def from_request(request, with_children=True, **kwargs):
        """
        Construct an `AnalysisControlLer` object from a request object.

        Parameters
        ----------
        request : rest_framework.request.Request
            REST request object
        with_children : bool, optional
            Also return analyses of children, i.e. of topographies that belong
            to a surface. (Default: True)

        Returns
        -------
        controller : AnalysisController
            The analysis controller object
        """
        user = request.user
        data = request.data | kwargs
        q = request.GET  # Querydict

        function_id = data.get("function_id")
        if function_id is None:
            function_id = q.get("function_id")
        if function_id is not None:
            function_id = int(function_id)

        subjects = data.get("subjects")
        if subjects is None:
            subjects = q.get("subjects")
        if subjects is not None and isinstance(subjects, str):
            subjects = dict_from_base64(subjects)

        function_kwargs = data.get("function_kwargs")
        if function_kwargs is None:
            function_kwargs = q.get("function_kwargs")
        if function_kwargs is not None and isinstance(function_kwargs, str):
            function_kwargs = dict_from_base64(function_kwargs)

        return AnalysisController(
            user,
            subjects=subjects,
            function_id=function_id,
            function_kwargs=function_kwargs,
            with_children=with_children,
        )

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
            self._subjects_without_analysis_results = (
                self._get_subjects_without_analysis_results()
            )
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
        return None if self._subjects is None else subjects_to_base64(self._subjects)

    def get(self, task_states=None, has_result_file=None):
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
        """
        if task_states is None:
            if has_result_file is None:
                analyses = self._analyses
            else:
                analyses = [
                    analysis
                    for analysis in self._analyses
                    if analysis.has_result_file == has_result_file
                ]
        else:
            if has_result_file is None:
                analyses = [
                    analysis
                    for analysis in self._analyses
                    if analysis.task_state in task_states
                ]
            else:
                analyses = [
                    analysis
                    for analysis in self._analyses
                    if analysis.task_state in task_states
                    and analysis.has_result_file == has_result_file
                ]
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
        # Return no results if subjects is empty list
        if len(self._subjects) == 0:
            return []

        # Query for user, function and subjects
        query = Q(user=self._user) & Q(function=self._function)

        # Query for subjects
        subjects_query = None
        for subject in self._subjects:
            q = AnalysisSubject.Q(subject)
            subjects_query = q if subjects_query is None else subjects_query | q
        query = subjects_query & query

        # Add kwargs (if specified)
        if self._function_kwargs is not None:
            query = Q(kwargs=self._function_kwargs) & query

        # Find and return analyses
        return (
            self.queryset.filter(query)
            .order_by(
                "subject_dispatch__topography_id",
                "subject_dispatch__surface_id",
                "subject_dispatch__tag_id",
                "-start_time",
            )
            .distinct(
                "subject_dispatch__topography_id",
                "subject_dispatch__surface_id",
                "subject_dispatch__tag_id",
            )
        )

    def _get_subjects_without_analysis_results(self):
        """Find analyses that are missing (i.e. have not yet run)"""
        # collect list of subjects for which an analysis instance is missing
        subjects_with_analysis_results = [
            analysis.subject for analysis in self._analyses
        ]
        if self._subjects is None:
            # If the no subjects are specified, then there are no subjects without analysis result by definition.
            # This controller is then simply returning the analyses that have run.
            subjects_without_analysis_results = []
        else:
            subjects_without_analysis_results = [
                subject
                for subject in self._subjects
                if subject not in subjects_with_analysis_results
            ]
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
        Automatically trigger analyses for missing subjects (tags,
        topographies or surfaces).

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
                try:
                    triggered_analysis = submit_analysis_if_missing(
                        self._user, self._function, subject, **function_kwargs
                    )
                    subjects_triggered += [subject]
                    _log.info(
                        f"Triggered analysis {triggered_analysis.id} for function '{self._function.name}' "
                        f"and subject '{subject}'."
                    )
                except ImplementationMissingAnalysisFunctionException:
                    _log.info(
                        f"Dit NOT trigger analysis for function '{self._function.name}' "
                        f"and subject '{subject}' because the implementation is missing."
                    )

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
            context = {"request": request}
        return [
            AnalysisResultSerializer(analysis, context=context).data
            for analysis in self.get(
                task_states=task_states, has_result_file=has_result_file
            )
        ]

    def get_analysis_ids(self, task_states=None, has_result_file=None):
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
        """
        return [
            analysis.id
            for analysis in self.get(
                task_states=task_states, has_result_file=has_result_file
            )
        ]

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
            "analyses": self.to_representation(
                task_states=task_states,
                has_result_file=has_result_file,
                request=request,
            ),
            "dois": self.dois,
            "functionName": self.function.name,
            "functionId": self.function.id,
            "subjects": self.subjects_dict,  # can be used to re-trigger analyses
            "uniqueKwargs": self.unique_kwargs,
            "hasNonuniqueKwargs": self.has_nonunique_kwargs,
        }
