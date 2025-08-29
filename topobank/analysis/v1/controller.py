import logging
from collections import defaultdict
from functools import reduce

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied

from ...manager.utils import dict_from_base64, subjects_from_dict, subjects_to_dict
from ..models import Analysis, AnalysisSubject, Workflow
from ..registry import WorkflowNotImplementedException
from ..serializers import ResultSerializer
from ..utils import find_children, merge_dicts

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
        workflow=None,
        workflow_name=None,
        kwargs=None,
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
        workflow : Workflow, optional
            Workflow function object. (Default: None)
        workflow_name : str, optional
            Name of analysis function. (Default: None)
        with_children : bool, optional
            Also return analyses of children, i.e. of topographies that belong
            to a surface. (Default: True)
        """
        self._user = user

        self._workflow = workflow
        if self._workflow is None:
            if workflow_name is not None:
                self._workflow = get_object_or_404(Workflow, name=workflow_name)
        if self._workflow is None:
            raise ValueError(
                "Please restrict this analysis controller to a specific workflow."
            )
        if not self._workflow.has_permission(user):
            raise PermissionDenied(
                f"User {self._user} does not have access to this workflow."
            )

        # Validate (and type convert) kwargs
        if kwargs is None or kwargs == {}:
            self._kwargs = None
        else:
            self._kwargs = self._workflow.clean_kwargs(kwargs)

        # Calculate subjects for the analyses, filtered for those which have an
        # implementation
        self._subjects = None
        if subjects is not None:
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

            # Surface permissions are checked in `subjects_from_dict`. Since children
            # (topographies) inherit the permission from their parents, we do not need to
            # do an additional permissions check.
            if with_children:
                self._subjects = find_children(self._subjects)

        # Find the latest analyses for which the user has read permission for the related data
        self._analyses = self._get_latest_analyses()

        self._reset_cache()

    @staticmethod
    def get_request_parameter(names, data, multiple=False):
        retdata = data.copy()

        def set_value_multiple(value, name):
            new_value = retdata.get(name, None)
            if value is None:
                if new_value is not None:
                    del retdata[name]
                    if isinstance(new_value, list):
                        return new_value
                    else:
                        return [new_value]
            elif new_value is not None:
                if isinstance(new_value, list):
                    return value + new_value
                else:
                    return value + [new_value]
            return value

        def set_value_single(value, name):
            new_value = retdata.get(name, None)
            if value is None:
                if new_value is not None:
                    if isinstance(new_value, list) and len(new_value) > 1:
                        errstr = reduce(lambda x, y: f"{x}, {y}", names)
                        raise ValueError(
                            f"Multiple values for query parameter '{errstr}'"
                        )
                    del retdata[name]
                    if isinstance(new_value, list):
                        (new_value,) = new_value
                return new_value
            elif new_value is not None:
                errstr = reduce(lambda x, y: f"{x}, {y}", names)
                raise ValueError(f"Multiple values for query parameter {errstr}")
            return value

        def set_value(value, name):
            if multiple:
                return set_value_multiple(value, name)
            else:
                return set_value_single(value, name)

        value = None
        for name in names:
            value = set_value(value, name)
        return value, retdata

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

        data = request.data | request.GET | kwargs
        workflow_name, data = AnalysisController.get_request_parameter(
            ["workflow"], data
        )

        subjects = defaultdict(list)
        subjects_str, data = AnalysisController.get_request_parameter(
            ["subjects"], data
        )
        if subjects_str is not None:
            subjects = defaultdict(list, dict_from_base64(subjects_str))

        for subject_key in _queryable_subjects:
            s, data = AnalysisController.get_request_parameter(
                [subject_key], data, multiple=True
            )
            if s is not None:
                try:
                    subjects[subject_key] += s
                except AttributeError:
                    raise ValueError(f"Malformed subject key '{subject_key}'")
                except ValueError:
                    raise ValueError(f"Malformed subject key '{subject_key}'")

        if len(subjects) == 0:
            subjects = None

        workflow_kwargs, data = AnalysisController.get_request_parameter(
            ["kwargs", "function_kwargs"], data
        )
        if workflow_kwargs is not None and isinstance(workflow_kwargs, str):
            workflow_kwargs = dict_from_base64(workflow_kwargs)


        if len(data) > 0:
            raise ValueError(
                "Unknown query parameters: "
                f"{reduce(lambda x, y: f'{x}, {y}', data.keys())}"
            )

        return AnalysisController(
            user,
            subjects=subjects,
            workflow_name=workflow_name,
            kwargs=workflow_kwargs,
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
    def workflow(self):
        return self._workflow

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
        # Return no results if subjects is empty list and theres no kwargs to filter
        # Having subject or kwargs to filter should be sufficient
        if (
            self._subjects is None or len(self._subjects) == 0
        ) and self._kwargs is None:
            return []

        # Query for user, function and subjects
        query = Q(permissions__user_permissions__user=self._user) & Q(
            function=self._workflow
        )

        # Query for subjects
        if self._subjects is not None and len(self._subjects):
            subjects_query = None
            for subject in self._subjects:
                q = AnalysisSubject.Q(subject)
                subjects_query = q if subjects_query is None else subjects_query | q
                # adjusting this fixes the latest query test
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
                "-task_start_time",
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
        if self._subjects is None or len(self._subjects) == 0:
            # If the no subjects are specified, then there are no subjects without
            # analysis result by definition. This controller is then simply returning
            # the analyses that have run.
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

        subjects_triggered = []
        for subject in self.subjects_without_analysis_results:
            if subject.is_shared(self._user):
                try:
                    triggered_analysis = self._workflow.submit(
                        self._user, subject, kwargs=kwargs
                    )
                    subjects_triggered += [subject]
                    _log.info(
                        f"Triggered workflow '{self._workflow.name}' for "
                        f"{subject} with kwargs '{triggered_analysis.kwargs}' "
                        f"(result id {triggered_analysis.id})."
                    )
                except WorkflowNotImplementedException:
                    _log.info(
                        f"Did NOT trigger workflow '{self._workflow.name}' because it "
                        f"does not have an implementation for {subject}."
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
            ResultSerializer(analysis, context=context).data
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
            "workflow_name": self.workflow.name,
            "subjects": self.subjects_dict,  # can be used to re-trigger analyses
            "unique_kwargs": self.unique_kwargs,
            "has_nonunique_kwargs": self.has_nonunique_kwargs,
        }
