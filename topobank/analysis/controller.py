from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from ..manager.utils import subjects_from_dict, subjects_to_dict

from .models import Analysis, AnalysisFunction
from .serializers import AnalysisSerializer


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

        # The following is needed for re-triggering analyses, now filtered
        # in order to trigger only for subjects which have an implementation
        self._subjects_dict = None if self._subjects is None else subjects_to_dict(self._subjects)

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
        function_kwargs = data.get('function_kwargs')

        return AnalysisController(user, subjects=subjects, function_id=function_id, function_kwargs=function_kwargs)

    def _reset_cache(self):
        self._dois = None
        self._unique_kwargs = None
        self._subjects_without_analysis_results = None

    @property
    def dois(self):
        if self._dois is None:
            self._dois = self._get_dois()
        return self._dois

    @property
    def unique_kwargs(self):
        if self._unique_kwargs is None:
            self._unique_kwargs = self._get_unique_kwargs()
        return self._unique_kwargs

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
        return self._subjects_dict

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

        # Query for subjects
        if self._subjects is not None:
            for subject in self._subjects:
                ct = ContentType.objects.get_for_model(subject)
                q = Q(subject_type_id=ct.id) & Q(subject_id=subject.id)
                query = q if query is None else query | q

        # Add function to query
        if self._function is not None:
            query = Q(function=self._function) & query

        # Add kwargs (if specified)
        if self._function_kwargs is not None:
            query = Q(kwargs=self._function_kwargs) & query

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
        return {} if unique_kwargs is None else unique_kwargs

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
        return [AnalysisSerializer(analysis, context=context).data for analysis in
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
            'uniqueKwargs': self.unique_kwargs
        }
