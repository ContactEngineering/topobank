"""
The Celery workflow engine's shim: `WorkflowImplementation`.

A `WorkflowImplementation` is a `WorkflowDescriptor` plus the code that runs
the workflow in-process in a Celery worker - the implementation methods keyed
by subject model, the dependencies they declare and the queue they run on.
Register subclasses with :data:`topobank.analysis.celery.engine.registry`.
"""

import inspect
import logging
import warnings

from muTimer import Timer

from ...manager.models import Surface, Tag, Topography
from ..descriptor import WorkflowDescriptor
from ..registry import WorkflowNotImplementedException

_log = logging.getLogger(__name__)


class WorkflowImplementation(WorkflowDescriptor):
    """
    A workflow that runs in-process in a Celery worker.

    This is the Celery workflow engine's shim: a `WorkflowDescriptor` (name,
    display name, parameters, outputs) plus the implementation methods
    themselves, keyed by subject model in ``Meta.implementations``, their
    declared dependencies and the queue they run on. Register subclasses with
    ``topobank.analysis.celery_manager.registry``.
    """

    class Meta:
        celery_queue = None
        implementations = {}
        dependencies = {}

    def __init__(self, **kwargs):
        self._kwargs = self.Parameters(**kwargs)

    @property
    def kwargs(self):
        return self._kwargs

    def _run_implementation(self, implementation, analysis, auxiliary_kwargs):
        """Invoke an implementation method with timing.

        The caller (the task runner) provides a ``timer`` (a ``muTimer.Timer``
        instance) via ``auxiliary_kwargs``. It is exposed to implementations as
        ``self.timer`` (so they can time individual steps, which nest under the
        workflow node) and is used here to record the total run time of the
        workflow under its name. Only keyword arguments the implementation
        actually accepts are forwarded, so the runner can pass extra context
        (e.g. ``timer``) without every implementation having to declare it.
        """
        self.timer = auxiliary_kwargs.get("timer") or Timer()
        signature = inspect.signature(implementation)
        accepts_var_keyword = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in signature.parameters.values()
        )
        # Forward the same timer instance so any sub-steps an implementation
        # times nest under the workflow's own timing node.
        forwarded = {**auxiliary_kwargs, "timer": self.timer}
        if not accepts_var_keyword:
            forwarded = {
                k: v for k, v in forwarded.items() if k in signature.parameters
            }
        with self.timer(self.Meta.name):
            return implementation(analysis, **forwarded)

    def eval(self, analysis, **auxiliary_kwargs):
        if analysis.subject is None and analysis.surfaces.exists():
            return self.eval_surfaces(analysis, **auxiliary_kwargs)
        implementation = self.get_implementation(analysis.subject.__class__)
        result = self._run_implementation(implementation, analysis, auxiliary_kwargs)
        if result is not None:
            warnings.warn(
                f"Workflow implementation '{self.Meta.name}' returned a result of type {type(result)}. "
                f"Returning results from workflows is deprecated. Please store results as files instead.",
                DeprecationWarning,
            )
        return result

    def eval_surfaces(self, analysis, **auxiliary_kwargs):
        """Evaluate using the surfaces M2M. Routes to existing implementations
        based on surface set size."""
        surfaces = list(analysis.surfaces.all())
        n = len(surfaces)

        if n > 1:
            if not self.has_implementation(Tag):
                raise WorkflowNotImplementedException(self.Meta.name, Tag)
            impl = self.get_implementation(Tag)
        elif n == 1:
            if self.has_implementation(Surface):
                impl = self.get_implementation(Surface)
            elif self.has_implementation(Topography):
                impl = self.get_implementation(Topography)
            else:
                raise WorkflowNotImplementedException(self.Meta.name, Surface)
        else:
            raise ValueError("No surfaces in analysis")

        result = self._run_implementation(impl, analysis, auxiliary_kwargs)
        if result is not None:
            warnings.warn(
                f"Workflow implementation '{self.Meta.name}' returned a result of type {type(result)}. "
                f"Returning results from workflows is deprecated. Please store results as files instead.",
                DeprecationWarning,
            )
        return result

    def get_implementation(self, model_class):
        """Returns the implementation function for a specific subject model"""
        try:
            name = self.Meta.implementations[model_class]
        except KeyError:
            raise WorkflowNotImplementedException(self.Meta.name, model_class)
        return getattr(self, name)

    @classmethod
    def has_implementation(cls, model_class):
        """
        Returns whether implementation function for a specific subject model exists
        """
        # The accepted subjects are the ones with an implementation method
        return model_class in cls.Meta.implementations

    def get_dependencies(self, analysis):
        """Return dependencies required for running analysis for `subject`"""
        _log.debug(
            f"Checking whether analysis function '{self.Meta.name}' has "
            f"dependency function for subject {analysis.subject} ..."
        )

        try:
            dependencies = self.Meta.dependencies
        except AttributeError:
            _log.debug("No dependency definition found.")
            return []

        # Surface set path: route based on surface count
        if analysis.surfaces.exists():
            return self._get_dependencies_for_surfaces(analysis, dependencies)

        try:
            dependency_func = getattr(self, dependencies[analysis.subject.__class__])
            _log.debug("Dependency function exists.")
        except KeyError:
            _log.debug(f"No dependency function for subject {analysis.subject} found.")
            dependencies = []
        else:
            dependencies = dependency_func(analysis)
        return dependencies

    def _get_dependencies_for_surfaces(self, analysis, dependencies):
        """Route dependency resolution based on surface set size."""
        surfaces = list(analysis.surfaces.all())
        n = len(surfaces)

        # More than one surface → use Tag-based dependency function
        if n > 1:
            dep_key = Tag
        # Exactly one surface → prefer Surface, fall back to Topography
        elif n == 1:
            dep_key = Surface if Surface in dependencies else Topography
        else:
            return []

        try:
            dependency_func = getattr(self, dependencies[dep_key])
            _log.debug("Dependency function exists for %s.", dep_key)
        except KeyError:
            _log.debug("No dependency function for surfaces (key=%s) found.", dep_key)
            return []

        return dependency_func(analysis)

    @staticmethod
    def _get_app_config_for_obj(klass):
        """For given object, find out app config it belongs to."""
        from django.apps import apps

        search_path = klass.__module__
        if search_path.startswith("topobank."):
            search_path = search_path[9:]  # otherwise app from topobank are not found
        app = None
        while app is None:
            try:
                app = apps.get_app_config(search_path)
            except LookupError:
                if ("." not in search_path) or app:
                    break
                search_path, _ = search_path.rsplit(".", 1)
        return app
