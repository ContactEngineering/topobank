"""
MuFlowWorkflowAdapter - Wraps muFlow TaskEntry to work with topobank's workflow system.

This adapter presents muFlow workflows as if they were WorkflowImplementations,
allowing them to be used seamlessly with topobank's existing analysis infrastructure.
"""

import logging
from typing import Optional

from django.conf import settings

from ...manager.models import Surface, Tag
from .converter import convert_surface_to_dataset, convert_tag_to_dataset

_log = logging.getLogger(__name__)


class MuFlowWorkflowMeta:
    """
    Meta class that mimics WorkflowImplementation.Meta for muFlow workflows.

    This provides the interface expected by topobank's registry and analysis system.
    """

    def __init__(self, entry):
        self._entry = entry

    @property
    def name(self):
        return self._entry.name

    @property
    def display_name(self):
        return self._entry.display_name

    @property
    def celery_queue(self):
        return self._entry.queue

    @property
    def implementations(self):
        """Return the supported subject types."""
        return {
            Tag: "tag_implementation",
            Surface: "surface_implementation",
        }

    @property
    def dependencies(self):
        """muFlow handles dependencies internally."""
        return {}


class MuFlowWorkflowAdapter:
    """
    Wraps a muFlow TaskEntry to work with topobank's workflow system.

    This adapter:
    1. Presents muFlow workflows as if they were WorkflowImplementations
    2. Converts Django models (Tag, Surface) to DatasetInfo
    3. Builds and submits TaskPlans to muFlow backend
    4. Handles result synchronization via completion callbacks
    """

    def __init__(self, entry, kwargs=None):
        """
        Initialize the adapter with a muFlow TaskEntry.

        Parameters
        ----------
        entry : TaskEntry
            The muFlow TaskEntry to wrap.
        kwargs : dict, optional
            Keyword arguments for the workflow. (Default: None)
        """
        self._entry = entry
        self._meta = MuFlowWorkflowMeta(entry)
        self.kwargs = kwargs or {}

    def __call__(self, **kwargs):
        """
        Make the adapter callable to mimic legacy workflow classes.

        In legacy TopoBank workflows, the class was instantiated with
        the kwargs of the analysis. This adapter mimics that behavior
        by returning a NEW instance with the updated kwargs.
        """
        return MuFlowWorkflowAdapter(self._entry, kwargs=kwargs)

    @property
    def Meta(self):
        """Return the Meta class for this workflow."""
        return self._meta

    @property
    def Parameters(self):
        """Return the Pydantic parameters model."""
        return self._entry.parameters

    @property
    def Outputs(self):
        """Return the outputs class."""
        return self._entry.outputs

    def __init_subclass__(cls, **kwargs):
        """Prevent subclassing - this is an adapter, not a base class."""
        raise TypeError("MuFlowWorkflowAdapter cannot be subclassed")

    @classmethod
    def clean_kwargs(cls, kwargs: dict, fill_missing: bool = True) -> dict:
        """
        Validate keyword arguments using the Pydantic model.

        This is a class method that doesn't have access to the instance,
        so it needs to be called on instances where we have the entry.
        """
        # This is called as a classmethod, but we need instance access
        # In practice, this is called on the instance
        raise NotImplementedError(
            "clean_kwargs must be called on an instance with _entry"
        )

    def instance_clean_kwargs(self, kwargs: Optional[dict], fill_missing: bool = True) -> dict:
        """
        Validate keyword arguments using the Pydantic model.

        Parameters
        ----------
        kwargs : dict | None
            Keyword arguments to validate.
        fill_missing : bool
            Fill missing keys with default values.

        Returns
        -------
        dict
            Validated keyword arguments.
        """
        if self._entry.parameters is None:
            return kwargs or {}

        if kwargs is None:
            if fill_missing:
                try:
                    return self._entry.parameters().model_dump()
                except Exception:
                    return {}
            else:
                return {}
        else:
            return self._entry.parameters(**kwargs).model_dump(
                exclude_unset=not fill_missing
            )

    @classmethod
    def get_outputs_schema(cls) -> list:
        """
        Get JSON schema for declared outputs.

        Returns
        -------
        list
            List of file descriptors with their schemas.
        """
        # This needs instance access to get the outputs
        return []

    def instance_get_outputs_schema(self) -> list:
        """
        Get JSON schema for declared outputs.

        Returns
        -------
        list
            List of file descriptors with their schemas.
        """
        if self._entry.outputs is None:
            return []

        from muflow import get_outputs_schema
        return get_outputs_schema(self._entry.outputs)

    def has_implementation(self, model_class) -> bool:
        """
        Check if this workflow has an implementation for the given model class.

        Parameters
        ----------
        model_class : type
            The model class to check (e.g., Tag, Surface).

        Returns
        -------
        bool
            True if the workflow supports this model class.
        """
        return model_class in self._meta.implementations

    def get_implementation(self, model_class):
        """
        Get the implementation method for a specific subject model.

        Parameters
        ----------
        model_class : type
            The model class (e.g., Tag, Surface).

        Returns
        -------
        callable
            The implementation method.

        Raises
        ------
        WorkflowNotImplementedException
            If no implementation exists for this model class.
        """
        from ..registry import WorkflowNotImplementedException

        if model_class not in self._meta.implementations:
            raise WorkflowNotImplementedException(self._meta.name, model_class)

        method_name = self._meta.implementations[model_class]
        return getattr(self, method_name)

    def get_dependencies(self, analysis):
        """
        Return dependencies required for running analysis.

        muFlow handles dependencies internally via its DAG system,
        so we return an empty list here.

        Parameters
        ----------
        analysis : WorkflowResult
            The analysis being executed.

        Returns
        -------
        list
            Empty list - muFlow handles dependencies.
        """
        return []

    def eval(self, analysis, **auxiliary_kwargs):
        """
        Execute the workflow for the given analysis.

        Parameters
        ----------
        analysis : WorkflowResult
            The analysis to execute.
        **auxiliary_kwargs
            Additional keyword arguments.

        Returns
        -------
        None
            Results are stored in files, not returned.
        """
        implementation = self.get_implementation(analysis.subject.__class__)
        return implementation(analysis, **auxiliary_kwargs)

    def tag_implementation(self, analysis, **auxiliary_kwargs):
        """
        Execute the workflow for a Tag subject.

        Parameters
        ----------
        analysis : WorkflowResult
            The analysis to execute. analysis.subject must be a Tag.
        **auxiliary_kwargs
            Additional keyword arguments.

        Returns
        -------
        None
            Results are stored in files.
        """
        tag = analysis.subject
        kwargs = analysis.kwargs or {}

        # Get property name from kwargs
        property_name = kwargs.get("property", "friction")

        # Convert Tag to DatasetInfo
        dataset = convert_tag_to_dataset(tag, property_name)

        # Merge dataset into kwargs
        workflow_kwargs = {**kwargs, "dataset": dataset}

        # Submit to muFlow
        return self._submit_to_muflow(analysis, workflow_kwargs)

    def surface_implementation(self, analysis, **auxiliary_kwargs):
        """
        Execute the workflow for a Surface subject.

        Parameters
        ----------
        analysis : WorkflowResult
            The analysis to execute. analysis.subject must be a Surface.
        **auxiliary_kwargs
            Additional keyword arguments.

        Returns
        -------
        None
            Results are stored in files.
        """
        surface = analysis.subject
        kwargs = analysis.kwargs or {}

        # Get property name from kwargs
        property_name = kwargs.get("property", "friction")

        # Convert Surface to DatasetInfo
        dataset = convert_surface_to_dataset(surface, property_name)

        # Merge dataset into kwargs
        workflow_kwargs = {**kwargs, "dataset": dataset}

        # Submit to muFlow
        return self._submit_to_muflow(analysis, workflow_kwargs)

    def _submit_to_muflow(self, analysis, kwargs):
        """
        Submit the workflow to muFlow for execution.

        Parameters
        ----------
        analysis : WorkflowResult
            The analysis to execute.
        kwargs : dict
            The workflow parameters including dataset.

        Returns
        -------
        None
            Results are stored in files after completion.
        """
        from muflow import Pipeline, Step
        from muflow import registry as muflow_registry
        from muflow.backends.callbacks import CeleryCompletionCallback

        # Build the subject key from the analysis
        subject = analysis.subject
        if isinstance(subject, Tag):
            subject_key = f"tag:{subject.id}"
        elif isinstance(subject, Surface):
            subject_key = f"surface:{subject.id}"
        else:
            subject_key = f"unknown:{subject.id}"

        # Get the muFlow backend
        backend = self._get_muflow_backend()

        # Build and submit the plan
        entry = muflow_registry.get(self._entry.name)
        if entry is None:
            raise RuntimeError(f"Workflow '{self._entry.name}' not found in muFlow registry")

        # Create a simple pipeline with just this task
        # The task's dependencies are handled by muFlow
        pipeline = Pipeline(
            name=f"topobank.{self._entry.name}",
            steps={
                "main": Step(task=self._entry.name),
            },
        )

        # Build the plan
        plan = pipeline.build_plan(subject_key, kwargs)

        # Create completion callback
        callback = CeleryCompletionCallback(
            task_name="topobank.analysis.muflow_bridge.on_muflow_complete",
            task_kwargs={"analysis_id": analysis.id},
        )

        # Submit to backend
        handle = backend.submit(plan, callback=callback)

        # Store the handle in analysis metadata for tracking
        if analysis.metadata is None:
            analysis.metadata = {}
        analysis.metadata["muflow_handle"] = handle.to_json()
        analysis.save(update_fields=["metadata"])

        _log.info(
            f"Submitted muFlow workflow '{self._entry.name}' for analysis {analysis.id}, "
            f"plan_id={handle.plan_id}"
        )

        return None

    def _get_muflow_backend(self):
        """
        Get the configured muFlow execution backend.

        Returns
        -------
        ExecutionBackend
            The configured backend (CeleryBackend for production).
        """
        from celery import current_app
        from muflow.backends import CeleryBackend
        from muflow.storage import S3StorageBackend

        # Get storage configuration from Django settings
        storage_prefix = getattr(settings, "MUFLOW_STORAGE_PREFIX", "muflow")
        bucket_name = getattr(settings, "MUFLOW_S3_BUCKET", None)
        if bucket_name is None:
            bucket_name = getattr(settings, "AWS_STORAGE_BUCKET_NAME", "topobank")

        # Create storage backend
        storage = S3StorageBackend(
            prefix=storage_prefix,
            bucket=bucket_name,
        )

        # Create and return CeleryBackend
        return CeleryBackend(
            celery_app=current_app,
            storage_backend=storage,
        )
