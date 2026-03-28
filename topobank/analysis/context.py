"""Django-integrated workflow context.

DjangoWorkflowContext wraps a WorkflowResult and its ManifestSet to provide
file I/O that works with Django's storage backend. It implements the
TopobankWorkflowContext protocol (which extends muflow.WorkflowContext),
allowing the same workflow code to run on both Django/Celery and serverless
backends.
"""

from typing import IO, Any, Optional, Protocol, runtime_checkable

import xarray as xr
from muflow import WorkflowContext

from topobank.analysis.models import WorkflowResult
from topobank.analysis.subjects import get_subject_metadata, resolve_subject
from topobank.files.models import ManifestSet
from topobank.taskapp.tasks import ProgressRecorder


@runtime_checkable
class TopobankWorkflowContext(WorkflowContext, Protocol):
    """Protocol for topobank workflow contexts.

    Extends WorkflowContext with topography access.  The three properties
    below (``topography``, ``topography_name``, ``topography_url``) are the
    contract that sds-workflows' ``execute(context)`` methods depend on.
    Every execution environment (Django/Celery, local runner, test harness)
    must provide a context that satisfies this protocol.

    Output Guards
    -------------
    The `allowed_outputs` property (inherited from WorkflowContext) controls
    which files a workflow can write:
    - None: No restriction (backward compatibility mode)
    - set(): Read-only context (used for dependency access)
    - set(["file1.json", "file2.nc"]): Only these files can be written
    """

    @property
    def topography(self) -> Any:
        """Return the topography data (SurfaceTopography or container)."""
        ...

    @property
    def topography_name(self) -> str:
        """Return the display name of the topography."""
        ...

    @property
    def topography_url(self) -> str:
        """Return the URL of the topography (may be empty)."""
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
    allowed_outputs : set[str] | None, optional
        Set of filenames this context is allowed to write.
        None means all writes allowed (default for backward compatibility).
        Empty set means read-only (used for dependency contexts).

    Example
    -------
    >>> ctx = DjangoWorkflowContext(analysis, dependencies)
    >>> ctx.save_json("result.json", {"accuracy": 0.95})
    >>> topography = ctx.topography  # Resolved SurfaceTopography
    >>> dep_result = ctx.dependency("feature_vectors").read_json("features.json")
    """

    def __init__(
        self,
        analysis: WorkflowResult,
        dependencies: Optional[dict[str, WorkflowResult]] = None,
        progress_recorder: Optional[ProgressRecorder] = None,
        allowed_outputs: Optional[set[str]] = None,
    ):
        self._analysis = analysis
        self._folder = analysis.folder
        self._kwargs = analysis.kwargs
        self._dependencies = dependencies or {}
        self._progress_recorder = progress_recorder
        self._allowed_outputs = allowed_outputs

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

    @property
    def allowed_outputs(self) -> set[str] | None:
        """Return set of allowed output filenames.

        Returns None if all writes are allowed (backward compatibility).
        Returns empty set if context is read-only (dependency contexts).
        Returns set of filenames if writes are restricted to declared outputs.
        """
        return self._allowed_outputs

    def _validate_write(self, filename: str) -> None:
        """Raise if filename is not in allowed_outputs."""
        if self._allowed_outputs is None:
            return  # No restriction
        if filename not in self._allowed_outputs:
            if not self._allowed_outputs:
                raise PermissionError(
                    f"Attempted to write '{filename}' to a read-only context"
                )
            raise PermissionError(
                f"Workflow attempted to write '{filename}' but only "
                f"{sorted(self._allowed_outputs)} are declared in Outputs"
            )

    # -------------------------------------------------------------------------
    # Topography access (implements TopobankWorkflowContext protocol)
    # -------------------------------------------------------------------------

    @property
    def topography(self) -> Any:
        """Return the resolved topography data.

        For topography workflows: SurfaceTopography object
        For surface workflows: ContainerProxy of SurfaceTopography objects
        """
        return self._subject

    @property
    def topography_name(self) -> str:
        """Return the display name of the topography."""
        return self._subject_name

    @property
    def topography_url(self) -> str:
        """Return the URL of the topography."""
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
        self._validate_write(filename)
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
        self._validate_write(filename)
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
        self._validate_write(filename)
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
        """Get a read-only context for accessing a completed dependency's outputs.

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
        # Dependencies are read-only - no progress recorder, empty allowed_outputs
        return DjangoWorkflowContext(
            dep_analysis,
            dependencies={},
            allowed_outputs=set(),  # Read-only
        )

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
    allowed_outputs: Optional[set[str]] = None,
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
    allowed_outputs : set[str] | None, optional
        Set of filenames this context is allowed to write.
        None means all writes allowed (default for backward compatibility).
        Empty set means read-only.

    Returns
    -------
    TopobankWorkflowContext
        A context implementing the TopobankWorkflowContext protocol.
    """
    return DjangoWorkflowContext(
        analysis, dependencies, progress_recorder, allowed_outputs
    )
