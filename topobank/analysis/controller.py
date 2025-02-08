import logging

from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

from ..manager.utils import dict_from_base64, subjects_from_dict, subjects_to_dict
from .models import Analysis, AnalysisFunction, AnalysisSubject
from .registry import ImplementationMissingAnalysisFunctionException
from .serializers import AnalysisResultSerializer
from .utils import find_children

_log = logging.getLogger(__name__)


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
        function_name=None,
        function_id=None,
        kwargs=None,
        with_children=True
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
        function_name : str, optional
            name of analysis function. (Default: None)
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
            if function_name is None:
                if function_id is None:
                    self._function = None
                else:
                    self._function = AnalysisFunction.objects.get(id=function_id)
            else:
                self._function = AnalysisFunction.objects.get(name=function_name)
        elif function_id is None:
            self._function = function
        else:
            raise ValueError(
                "Please provide either `function`, `function_id` or `function_name`, "
                "not multiple."
            )

        print("self_function =", self._function)

        if self._function is None:
            raise ValueError(
                "Please restrict this analysis controller to a specific function."
            )

        if not self._function.has_permission(user):
            raise PermissionDenied(
                f"User {self._user} does not have access to this analysis function."
            )

        # Validate (and type convert) kwargs
        self._kwargs = self._function.clean_kwargs(kwargs, fill_missing=False)
        if self._kwargs == {}:
            self._kwargs = None

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
            except PermissionDenied:
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
        _queryable_subjects = ["tag", "surface", "topography"]

        user = request.user
        data = request.data | kwargs
        q = request.GET  # Querydict

        function_id = None
        function_name = data.get("function_name")
        if function_name is None:
            function_name = q.get("function_name")
        if function_name is None:
            function_id = data.get("function_id")
            if function_id is None:
                function_id = q.get("function_id")
            if function_id is None:
                raise ValueError("You need to provide a function name or id")
            else:
                function_id = int(function_id)

        subjects = data.get("subjects")
        if subjects is None:
            subjects = q.get("subjects")
        if subjects is not None and isinstance(subjects, str):
            subjects = dict_from_base64(subjects)

        if subjects is None:
            for subject_key in _queryable_subjects:
                subject = q.get(subject_key)
                if subject is not None:
                    if subjects is None:
                        subjects = {}
                    try:
                        if subject_key == "tag":
                            subjects[subject_key] = [subject]
                        else:
                            subjects[subject_key] = [int(x) for x in subject.split(',')]
                    except AttributeError:
                        raise ValueError(f"Malformed subject key '{subject_key}'")
                    except ValueError:
                        raise ValueError(f"Malformed subject key '{subject_key}'")

        kwargs = data.get("function_kwargs")
        if kwargs is None:
            kwargs = q.get("function_kwargs")
        if kwargs is not None and isinstance(kwargs, str):
            kwargs = dict_from_base64(kwargs)

        return AnalysisController(
            user,
            subjects=subjects,
            function_name=function_name,
            function_id=function_id,
            kwargs=kwargs,
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
        query = Q(permissions__user_permissions__user=self._user) & Q(
            function=self._function
        )

        # Query for subjects
        subjects_query = None
        for subject in self._subjects:
            q = AnalysisSubject.Q(subject)
            subjects_query = q if subjects_query is None else subjects_query | q
        query = subjects_query & query

        # Add kwargs (if specified)
        if self._kwargs is not None:
            query = Q(kwargs=self._kwargs) & query

        # Find and return analyses
        qs = (
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

        # This is part of the migrations. For any analysis that has no folder,
        # traverse the S3 and find all files. This will only run once.
        for analysis in qs.filter(folder__isnull=True).all():
            analysis.fix_folder()

        return qs

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

        kwargs = self.unique_kwargs
        # Manually provided function kwargs override unique kwargs from prior analysis query
        if self._kwargs is not None:
            kwargs.update(self._kwargs)

        # For every possible implemented subject type the following is done:
        # We use the common unique keyword arguments if there are any; if not
        # the default arguments for the implementation is used

        subjects_triggered = []
        for subject in self.subjects_without_analysis_results:
            if subject.is_shared(self._user):
                try:
                    triggered_analysis = self._function.submit(
                        self._user, subject, kwargs=kwargs
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
            "function_name": self.function.name,
            "function_id": self.function.id,
            "subjects": self.subjects_dict,  # can be used to re-trigger analyses
            "unique_kwargs": self.unique_kwargs,
            "has_nonunique_kwargs": self.has_nonunique_kwargs,
        }
