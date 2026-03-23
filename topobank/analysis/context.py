"""Django-integrated workflow context.

DjangoWorkflowContext wraps a WorkflowResult and its ManifestSet to provide
file I/O that works with Django's storage backend. It implements the
TopobankWorkflowContext protocol (which extends muflows.WorkflowContext),
allowing the same workflow code to run on both Django/Celery and serverless
backends.
"""

from typing import IO, Any, Optional, Protocol, runtime_checkable

import xarray as xr
from muflows import WorkflowContext

from topobank.analysis.models import WorkflowResult
from topobank.analysis.subjects import get_subject_metadata, resolve_subject
from topobank.files.models import ManifestSet
from topobank.taskapp.tasks import ProgressRecorder


@runtime_checkable
class TopobankWorkflowContext(WorkflowContext, Protocol):
    """Protocol for topobank workflow contexts.

    Extends WorkflowContext with subject access for topography data.
    This allows workflows to access the SurfaceTopography object being
    analyzed without depending on Django models.
    """

    @property
    def subject(self) -> Any:
        """Return the subject data (SurfaceTopography or container)."""
        ...

    @property
    def subject_name(self) -> str:
        """Return the display name of the subject."""
        ...

    @property
    def subject_url(self) -> str:
        """Return the URL of the subject (may be empty)."""
        ...


class DjangoWorkflowContext:
    """WorkflowContext backed by Django ORM.

    This context wraps a WorkflowResult and uses its ManifestSet for file I/O.
    It is used when running workflows inside Celery workers with full Django access.

    Implements TopobankWorkflowContext protocol, which extends WorkflowContext
    with subject access (subject, subject_name, subject_url).

    Parameters
    ----------
    analysis : WorkflowResult
        The workflow result being executed.
    dependencies : dict[str, WorkflowResult], optional
        Mapping from dependency key to completed WorkflowResult.
    progress_recorder : ProgressRecorder, optional
        For reporting task progress to Celery.

    Example
    -------
    >>> ctx = DjangoWorkflowContext(analysis, dependencies)
    >>> ctx.save_json("result.json", {"accuracy": 0.95})
    >>> topography = ctx.subject  # Resolved SurfaceTopography
    >>> dep_result = ctx.dependency("feature_vectors").read_json("features.json")
    """

    def __init__(
        self,
        analysis: WorkflowResult,
        dependencies: Optional[dict[str, WorkflowResult]] = None,
        progress_recorder: Optional[ProgressRecorder] = None,
    ):
        self._analysis = analysis
        self._folder = analysis.folder
        self._kwargs = analysis.kwargs
        self._dependencies = dependencies or {}
        self._progress_recorder = progress_recorder

        # Subject resolution - convert Django model to native object
        self._subject = resolve_subject(analysis.subject)
        self._subject_name, self._subject_url = get_subject_metadata(analysis.subject)

    @property
    def storage_prefix(self) -> str:
        """Return the storage prefix for this workflow's output files.

        Returns the ManifestSet's storage_prefix if set, otherwise returns
        an empty string (legacy mode uses Manifest.pk-based paths).
        """
        return self._folder.storage_prefix or ""

    @property
    def kwargs(self) -> dict:
        """Return the workflow parameters."""
        return self._kwargs

    # -------------------------------------------------------------------------
    # Subject access (implements TopobankWorkflowContext protocol)
    # -------------------------------------------------------------------------

    @property
    def subject(self) -> Any:
        """Return the resolved subject data.

        For topography workflows: SurfaceTopography object
        For surface workflows: ContainerProxy of SurfaceTopography objects
        """
        return self._subject

    @property
    def subject_name(self) -> str:
        """Return the display name of the subject."""
        return self._subject_name

    @property
    def subject_url(self) -> str:
        """Return the URL of the subject."""
        return self._subject_url

    # -------------------------------------------------------------------------
    # Django-specific access (use sparingly for portability)
    # -------------------------------------------------------------------------

    @property
    def analysis(self) -> WorkflowResult:
        """Return the underlying WorkflowResult.

        This provides access to Django-specific functionality.
        Use sparingly - prefer the context methods for portability.
        """
        return self._analysis

    @property
    def folder(self) -> ManifestSet:
        """Return the underlying ManifestSet.

        This provides access to Django-specific functionality.
        Use sparingly - prefer the context methods for portability.
        """
        return self._folder

    # -------------------------------------------------------------------------
    # File I/O (implements WorkflowContext protocol)
    # -------------------------------------------------------------------------

    def save_file(self, filename: str, data: bytes) -> None:
        """Save raw bytes to a file.

        Parameters
        ----------
        filename : str
            Name of the file to save.
        data : bytes
            Raw bytes to write.
        """
        from django.core.files.base import ContentFile
        self._folder.save_file(filename, "der", ContentFile(data))

    def save_json(self, filename: str, data: Any) -> None:
        """Save data as JSON.

        Parameters
        ----------
        filename : str
            Name of the file to save.
        data : Any
            Data to serialize to JSON.
        """
        self._folder.save_json(filename, data)

    def save_xarray(self, filename: str, dataset: xr.Dataset) -> None:
        """Save an xarray Dataset as NetCDF.

        Parameters
        ----------
        filename : str
            Name of the file to save.
        dataset : xr.Dataset
            Dataset to save.
        """
        self._folder.save_xarray(filename, dataset)

    def open_file(self, filename: str, mode: str = "r") -> IO:
        """Open a file for reading.

        Parameters
        ----------
        filename : str
            Name of the file to open.
        mode : str, optional
            File mode ('r' for text, 'rb' for binary). Default is 'r'.

        Returns
        -------
        IO
            File-like object.
        """
        return self._folder.open_file(filename, mode)

    def read_file(self, filename: str) -> bytes:
        """Read raw bytes from a file.

        Parameters
        ----------
        filename : str
            Name of the file to read.

        Returns
        -------
        bytes
            Raw file contents.
        """
        with self._folder.open_file(filename, mode="rb") as f:
            return f.read()

    def read_json(self, filename: str) -> Any:
        """Read and parse a JSON file.

        Parameters
        ----------
        filename : str
            Name of the file to read.

        Returns
        -------
        Any
            Parsed JSON data.
        """
        return self._folder.read_json(filename)

    def read_xarray(self, filename: str) -> xr.Dataset:
        """Read a NetCDF file as xarray Dataset.

        Parameters
        ----------
        filename : str
            Name of the file to read.

        Returns
        -------
        xr.Dataset
            Loaded dataset.
        """
        return self._folder.read_xarray(filename)

    def exists(self, filename: str) -> bool:
        """Check if a file exists.

        Parameters
        ----------
        filename : str
            Name of the file to check.

        Returns
        -------
        bool
            True if file exists.
        """
        return self._folder.exists(filename)

    # -------------------------------------------------------------------------
    # Dependency access
    # -------------------------------------------------------------------------

    def dependency(self, key: str) -> "DjangoWorkflowContext":
        """Get a context for accessing a completed dependency's outputs.

        Parameters
        ----------
        key : str
            Dependency key as declared in the workflow's dependencies.

        Returns
        -------
        DjangoWorkflowContext
            Context for the dependency's outputs (read-only).

        Raises
        ------
        KeyError
            If the dependency key is not found.
        """
        if key not in self._dependencies:
            raise KeyError(
                f"Unknown dependency: '{key}'. "
                f"Available dependencies: {list(self._dependencies.keys())}"
            )
        dep_analysis = self._dependencies[key]
        # Dependencies are read-only - no progress recorder
        return DjangoWorkflowContext(dep_analysis, dependencies={})

    def has_dependency(self, key: str) -> bool:
        """Check if a dependency exists.

        Parameters
        ----------
        key : str
            Dependency key to check.

        Returns
        -------
        bool
            True if dependency exists.
        """
        return key in self._dependencies

    def dependency_keys(self) -> list[str]:
        """Get list of available dependency keys.

        Returns
        -------
        list[str]
            Available dependency keys.
        """
        return list(self._dependencies.keys())

    # -------------------------------------------------------------------------
    # Progress reporting
    # -------------------------------------------------------------------------

    def report_progress(self, current: int, total: int, message: str = "") -> None:
        """Report task progress.

        Parameters
        ----------
        current : int
            Current step number.
        total : int
            Total number of steps.
        message : str, optional
            Progress message.
        """
        if self._progress_recorder is not None:
            self._progress_recorder.set_progress(current, total, message)


# Factory function that returns TopobankWorkflowContext type.
# This allows static type checkers to verify DjangoWorkflowContext implements
# the TopobankWorkflowContext protocol (the return type annotation enforces this).
def create_workflow_context(
    analysis: WorkflowResult,
    dependencies: Optional[dict[str, WorkflowResult]] = None,
    progress_recorder: Optional[ProgressRecorder] = None,
) -> TopobankWorkflowContext:
    """Create a workflow context for the given analysis.

    This factory function returns a TopobankWorkflowContext, which allows static
    type checkers to verify that DjangoWorkflowContext correctly implements the
    protocol defined in topobank_statistics.

    Parameters
    ----------
    analysis : WorkflowResult
        The workflow result being executed.
    dependencies : dict[str, WorkflowResult], optional
        Mapping from dependency key to completed WorkflowResult.
    progress_recorder : ProgressRecorder, optional
        For reporting task progress to Celery.

    Returns
    -------
    TopobankWorkflowContext
        A context implementing the TopobankWorkflowContext protocol.
    """
    return DjangoWorkflowContext(analysis, dependencies, progress_recorder)
