"""Workflow planning: builds execution DAGs for workflows with dependencies.

The WorkflowPlanner constructs a complete execution plan (DAG) before any
computation begins. This allows:
- Upfront validation of the entire workflow graph
- Content-addressed caching (reuse existing results)
- Backend-agnostic execution (same plan can run on Celery, Lambda, etc.)
"""

import logging
from typing import Union

from django.db.models import Q
from muflow import WorkflowNode, WorkflowPlan, compute_prefix

from topobank.analysis.models import Workflow, WorkflowResult, WorkflowSubject
from topobank.manager.models import Surface, Tag, Topography

_log = logging.getLogger(__name__)


def get_subject_key(subject: Union[Tag, Topography, Surface]) -> str:
    """Generate a unique key for a subject.

    Parameters
    ----------
    subject : Tag, Topography, or Surface
        The workflow subject.

    Returns
    -------
    str
        A unique key like "topography:123" or "surface:456".
    """
    if isinstance(subject, Topography):
        return f"topography:{subject.id}"
    elif isinstance(subject, Surface):
        return f"surface:{subject.id}"
    elif isinstance(subject, Tag):
        return f"tag:{subject.id}"
    else:
        raise TypeError(f"Unknown subject type: {type(subject)}")


class WorkflowPlanner:
    """Builds the full execution DAG for a workflow and its dependencies.

    The planner recursively resolves all dependencies, checks for cached results,
    and constructs a static WorkflowPlan that can be serialized and executed.

    Example
    -------
    >>> planner = WorkflowPlanner()
    >>> plan = planner.build_plan(
    ...     function_name="sds_ml.v3.gpr.training",
    ...     subject=my_topography,
    ...     kwargs={"kernel": "rbf"},
    ...     user=current_user,
    ... )
    >>> # plan.nodes contains all workflow nodes
    >>> # plan.root_key identifies the requested workflow
    """

    def __init__(self, check_cache: bool = True):
        """Initialize the planner.

        Parameters
        ----------
        check_cache : bool, optional
            Whether to check for existing cached results. Default True.
        """
        self._check_cache = check_cache

    def build_plan(
        self,
        function_name: str,
        subject: Union[Tag, Topography, Surface],
        kwargs: dict,
        user=None,
    ) -> WorkflowPlan:
        """Build a complete execution plan for a workflow.

        Parameters
        ----------
        function_name : str
            Name of the workflow function (e.g., "sds_ml.v3.gpr.training").
        subject : Tag, Topography, or Surface
            The subject of the workflow.
        kwargs : dict
            Keyword arguments for the workflow.
        user : User, optional
            User requesting the workflow (for permission checks on cache).

        Returns
        -------
        WorkflowPlan
            Complete execution plan with all nodes.
        """
        nodes: dict[str, WorkflowNode] = {}
        root_key = self._resolve(function_name, subject, kwargs, nodes, user)

        # Compute reverse edges (depended_on_by)
        for node in nodes.values():
            for dep_key in node.depends_on:
                if dep_key in nodes:
                    nodes[dep_key].depended_on_by.append(node.key)

        return WorkflowPlan(nodes=nodes, root_key=root_key)

    def _resolve(
        self,
        function_name: str,
        subject: Union[Tag, Topography, Surface],
        kwargs: dict,
        nodes: dict[str, WorkflowNode],
        user=None,
    ) -> str:
        """Recursively resolve a workflow and its dependencies.

        Parameters
        ----------
        function_name : str
            Name of the workflow function.
        subject : Tag, Topography, or Surface
            The subject of the workflow.
        kwargs : dict
            Keyword arguments for the workflow.
        nodes : dict
            Accumulator for discovered nodes.
        user : User, optional
            User for permission checks.

        Returns
        -------
        str
            The node key for this workflow.
        """
        subject_key = get_subject_key(subject)
        hash_dict = {
            "workflow": function_name,
            "subject": subject_key,
            **kwargs,
        }
        storage_prefix = compute_prefix(hash_dict)

        # Node key is derived from storage prefix (content-addressed)
        node_key = storage_prefix

        # Already processed this node?
        if node_key in nodes:
            return node_key

        # Check for cached result
        cached = False
        analysis_id = None
        if self._check_cache:
            cached_result = self._find_cached_result(
                function_name, subject, kwargs, user
            )
            if cached_result is not None:
                cached = True
                analysis_id = cached_result.id
                _log.debug(f"Found cached result for {node_key}: {cached_result.id}")

        # Get workflow implementation to discover dependencies
        try:
            workflow = Workflow.objects.get(name=function_name)
            impl = workflow.implementation
        except Workflow.DoesNotExist:
            raise ValueError(f"Unknown workflow: {function_name}")

        # Get output files from implementation (if declared)
        output_files = []
        if hasattr(impl, "get_outputs_schema"):
            outputs_schema = impl.get_outputs_schema()
            output_files = [f["filename"] for f in outputs_schema if "filename" in f]

        # Create the node
        node = WorkflowNode(
            key=node_key,
            function=function_name,
            subject_key=subject_key,
            kwargs=kwargs,
            storage_prefix=storage_prefix,
            depends_on=[],
            depended_on_by=[],
            output_files=output_files,
            cached=cached,
            analysis_id=analysis_id,
        )
        nodes[node_key] = node

        # Resolve dependencies (if not cached - cached nodes don't need deps resolved)
        if not cached:
            dependencies = self._get_dependencies(impl, subject, kwargs)
            for dep_key, dep_spec in dependencies.items():
                dep_function = dep_spec["function"]
                dep_subject = dep_spec.get("subject", subject)
                dep_kwargs = dep_spec.get("kwargs", {})

                dep_node_key = self._resolve(
                    dep_function, dep_subject, dep_kwargs, nodes, user
                )
                node.depends_on.append(dep_node_key)

        return node_key

    def _find_cached_result(
        self,
        function_name: str,
        subject: Union[Tag, Topography, Surface],
        kwargs: dict,
        user=None,
    ) -> "WorkflowResult | None":
        """Find an existing successful result for this workflow.

        Parameters
        ----------
        function_name : str
            Name of the workflow function.
        subject : Tag, Topography, or Surface
            The subject of the workflow.
        kwargs : dict
            Keyword arguments for the workflow.
        user : User, optional
            User for permission filtering.

        Returns
        -------
        WorkflowResult or None
            Existing successful result, or None if not found.
        """
        try:
            workflow = Workflow.objects.get(name=function_name)
        except Workflow.DoesNotExist:
            return None

        # Build query for matching results
        q = (
            WorkflowSubject.Q(subject)
            & Q(function=workflow)
            & Q(kwargs=kwargs)
            & Q(task_state=WorkflowResult.SUCCESS)
            & Q(deprecation_time__isnull=True)
        )

        # Filter by user permissions if provided
        if user is not None:
            results = WorkflowResult.objects.for_user(user).filter(q)
        else:
            results = WorkflowResult.objects.filter(q)

        return results.order_by("-task_start_time").first()

    def _get_dependencies(
        self,
        impl,
        subject: Union[Tag, Topography, Surface],
        kwargs: dict,
    ) -> dict:
        """Get dependencies declared by a workflow implementation.

        Parameters
        ----------
        impl : WorkflowImplementation
            The workflow implementation class.
        subject : Tag, Topography, or Surface
            The subject of the workflow.
        kwargs : dict
            Keyword arguments for the workflow.

        Returns
        -------
        dict
            Mapping from dependency key to dependency specification.
            Each spec has: {"function": str, "subject": optional, "kwargs": dict}
        """
        # Check if implementation declares dependencies
        if not hasattr(impl, "get_dependencies_spec"):
            return {}

        try:
            # Instantiate the implementation to get dependencies
            runner = impl(**kwargs)
            if hasattr(runner, "get_dependencies_spec"):
                return runner.get_dependencies_spec(subject)
        except Exception as e:
            _log.warning(f"Failed to get dependencies for {impl}: {e}")

        return {}
