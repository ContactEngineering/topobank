import logging

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404

from topobank.manager.utils import subjects_from_dict, subjects_to_dict
from topobank.analysis.models import Workflow, WorkflowResult, WorkflowSubject
from topobank.analysis.registry import WorkflowNotImplementedException
from topobank.analysis.utils import find_children

_log = logging.getLogger(__name__)


class AnalysisController:
    """Retrieve and toggle status of analyses"""

    queryset = WorkflowResult.objects.all().select_related(
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
                    if hasattr(subject, "has_permission"):
                        if subject.has_permission(self._user, "view"):
                            self._subjects.append(subject)
                    else:
                        if hasattr(subject, "authorize_user"):
                            subject.authorize_user(self._user, "view")
                        related_surfaces = subject.get_related_surfaces()
                        if all(
                            s.has_permission(self._user, "view")
                            for s in related_surfaces
                        ):
                            self._subjects.append(subject)
                except (PermissionDenied, TypeError):
                    # Skip subjects that the user is not allowed to view or where
                    # permission method signatures are incompatible.
                    continue

            # Surface permissions are checked in `subjects_from_dict`. Since children
            # (topographies) inherit the permission from their parents, we do not need to
            # do an additional permissions check.
            if with_children:
                self._subjects = find_children(self._subjects)

        # Find the latest analyses for which the user has read permission for the related data
        self._analyses = self._get_latest_analyses()

        self._reset_cache()

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
                q = WorkflowSubject.Q(subject)
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
