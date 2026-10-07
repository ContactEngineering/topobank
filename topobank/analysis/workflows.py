"""
Building blocks shared by workflows and the code that submits them.

Nothing in this module runs a workflow or knows how one is run. It holds what
every workflow engine and every shim has in common: how a set of surfaces is
identified (`SurfaceSet`, `compute_subject_hash`), how a result is asked for
(`ResultRequest` - the same value object whether a user submits a workflow or a
workflow declares a dependency), and helpers that implementations use to
build their results (`ContainerProxy`, `wrap_series`, `make_alert_entry`,
`reasonable_bins_argument`).

The Celery engine's shim, `WorkflowImplementation`, lives in
:mod:`topobank.analysis.celery.workflows`; it is still importable from here for
callers written before workflow engines existed.
"""

import collections
import hashlib
import logging
import warnings
from dataclasses import dataclass, field
from typing import List, Optional, Union

import numpy as np
import pydantic
from pydantic import field_validator

from ..manager.models import Surface, Tag, Topography
from ..supplib.dict import SplitDictionaryHere

_log = logging.getLogger(__name__)


def compute_subject_hash(subject_type: str, subject_ids):
    """Compute a deterministic hash for a set of subject IDs, prefixed by type."""
    sorted_ids = sorted(set(subject_ids))
    key = ",".join(str(sid) for sid in sorted_ids)
    return f"{subject_type}:{hashlib.sha256(key.encode()).hexdigest()}"


class SurfaceSet(pydantic.BaseModel):
    """Validates and normalizes a set of surface IDs for workflow submission."""

    surfaces: list[int]

    @field_validator("surfaces")
    @classmethod
    def validate_surfaces(cls, v):
        if not v:
            raise ValueError("At least one surface required")
        return sorted(set(v))

    @property
    def subject_hash(self) -> str:
        return compute_subject_hash("surfaces", self.surfaces)


class WorkflowError(Exception):
    """Error for signaling problems in workflows."""

    pass


class ContainerProxy(collections.abc.Iterator):
    """
    Proxy class that emulates a SurfaceTopography `Container` and can be used
    to iterate over native SurfaceTopography objects.
    """

    def __init__(self, obj):
        self._obj = obj
        self._iter = iter(obj)

    def __len__(self):
        return len(self._obj)

    def __iter__(self):
        return ContainerProxy(self._obj)

    def __next__(self):
        return next(self._iter).topography()


def reasonable_bins_argument(topography):
    """Returns a reasonable 'bins' argument for np.histogram for given topography's heights.

    :param topography: Line scan or topography from SurfaceTopography module
    :return: argument for 'bins' argument of np.histogram
    """
    if topography.is_uniform:
        return int(np.sqrt(np.prod(topography.nb_grid_pts)) + 1.0)
    else:
        return int(
            np.sqrt(np.prod(len(topography.positions()))) + 1.0
        )  # TODO discuss whether auto or this
        # return 'auto'


def _finite_range(values):
    """Smallest and largest finite value of a data series.

    Parameters
    ----------
    values : array_like
        The data.

    Returns
    -------
    list of float or None
        `[minimum, maximum]`, or None if nothing in the series is finite. Series
        can carry NaN (an undefined data point) and infinities (a distribution
        that diverges), neither of which says anything about the extent of the
        data.
    """
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return None
    return [float(finite.min()), float(finite.max())]


def wrap_series(series, primary_key="x"):
    """
    Wrap each data series into a `SplitDictionaryHere` with a consecutive name
    'series-0', 'series-1'. Each `SplitDictionaryHere` is written into a separate
    file by `store_split_dict`.

    Parameters
    ----------
    series : list
        The list of data series to be wrapped.
    primary_key : str, optional
        The primary key for the data series. Default is 'x'.

    Returns
    -------
    wrapped_series : list
        The list of wrapped data series.
    """
    wrapped_series = []
    for i, s in enumerate(series):
        supplementary = {"name": s["name"], "nbDataPoints": len(s[primary_key])}
        if "visible" in s:
            supplementary["visible"] = s["visible"]
        # The extent of the data, recorded here because this is where the series
        # is still in memory. A plot that combines several results needs it to
        # choose a display unit that suits the data, and reading the series back
        # out of the object store to find out would defeat the purpose of
        # splitting them off (ContactEngineering/ce-ui#39).
        for axis, key in (("x", primary_key), ("y", "y")):
            if key in s:
                data_range = _finite_range(s[key])
                if data_range is not None:
                    supplementary[f"{axis}Range"] = data_range
        wrapped_series.append(
            SplitDictionaryHere(f"series-{i}", s, supplementary=supplementary)
        )
    return wrapped_series


def make_alert_entry(
    level, subject_name, data_series_name, detail_mesg, subject_url=None
):
    """Build string with alert message often used in the functions.

    Parameters
    ----------
    level: str
        One of ['info', 'warning', 'danger'], see also alert classes in bootstrap 4
    subject_name: str
        Name of the subject.
    data_series_name: str
        Name of the data series this applies to.
    detail_mesg: str
        Details about the alert.
    subject_url: str, optional
        URL of the subject. When given, the subject name is rendered as a link;
        otherwise the plain name is used. Analysis workers no longer build routed
        URLs (core is REST/UI-agnostic), so this is left unset there.

    Returns
    -------
    str
    """
    if subject_url:
        subject = f'<a class="alert-link" href="{subject_url}">{subject_name}</a>'
    else:
        subject = subject_name
    message = f"Failure for digital surface twin {subject}, data series '{data_series_name}': {detail_mesg}"
    return dict(alert_class=f"alert-{level}", message=message)


@dataclass
class ResultRequest:
    """
    What a caller asks for: a workflow, applied to a subject, with parameters.

    This is the single value object behind both ways a `WorkflowResult` comes
    into being - a user submitting a workflow (`Workflow.submit`,
    `Workflow.submit_for_surfaces`) and a workflow declaring a dependency
    (`Meta.dependencies` on the Celery shim). `topobank.analysis.store`
    turns a request into a result row, reusing an existing one where the
    caller's reuse policy allows.

    Exactly one of `subject` and `surfaces` is set. `subject` is a single
    `Topography`, `Surface` or `Tag`, stored on the result's foreign keys;
    `surfaces` is a set of surfaces, stored on the result's `surfaces`
    relation and identified by `subject_hash`.

    `kwargs` are the parameters as given; they are validated and completed
    against the workflow's `Parameters` model when the request is resolved,
    not here, so a request is cheap to build and never touches the registry.
    """

    workflow_name: str
    subject: Union[Surface, Topography, Tag, None] = None
    surfaces: Optional[List[Surface]] = None
    kwargs: Optional[dict] = field(default=None)

    def __post_init__(self):
        if (self.subject is None) == (self.surfaces is None):
            raise ValueError(
                "A ResultRequest needs exactly one of `subject` and `surfaces`."
            )
        if self.surfaces is not None:
            self.surfaces = list(self.surfaces)
            if len(self.surfaces) == 0:
                raise ValueError("A ResultRequest for a surface set needs at least one surface.")
        elif not isinstance(self.subject, (Surface, Topography, Tag)):
            raise ValueError(
                "`subject` must be a `Tag`, `Topography` or `Surface`, "
                f"not {type(self.subject)}."
            )

    @property
    def subject_type(self) -> str:
        """The subject type as used in `subject_hash`: 'surfaces', 'surface', 'topography' or 'tag'."""
        if self.surfaces is not None:
            return "surfaces"
        if isinstance(self.subject, Tag):
            return "tag"
        if isinstance(self.subject, Topography):
            return "topography"
        return "surface"

    @property
    def subject_ids(self) -> List[int]:
        if self.surfaces is not None:
            return [s.id for s in self.surfaces]
        return [self.subject.id]

    @property
    def subject_hash(self) -> str:
        """Deterministic identifier of the subject, as stored on `WorkflowResult.subject_hash`."""
        return compute_subject_hash(self.subject_type, self.subject_ids)

    def as_surface_set(self) -> "ResultRequest":
        """
        The same request with a `Surface` subject turned into a one-surface set.

        Dependencies of a surface-set result are themselves surface-set
        results, so that a parent and its dependencies share one addressing
        scheme. Requests that are already surface sets, or whose subject is a
        topography or tag, are returned unchanged.
        """
        if self.surfaces is None and isinstance(self.subject, Surface):
            return ResultRequest(
                workflow_name=self.workflow_name,
                surfaces=[self.subject],
                kwargs=self.kwargs,
            )
        return self


class WorkflowDefinition(ResultRequest):
    """
    Deprecated spelling of `ResultRequest` with a `Workflow` in place of the name.

    Kept for dependency declarations written as
    ``WorkflowDefinition(subject=..., function=Workflow(name=...), kwargs=...)``.
    New code builds a `ResultRequest` with `workflow_name`.
    """

    def __init__(self, subject=None, function=None, kwargs=None, workflow_name=None):
        warnings.warn(
            "WorkflowDefinition is deprecated; declare dependencies as "
            "ResultRequest(workflow_name=..., subject=..., kwargs=...).",
            DeprecationWarning,
            stacklevel=2,
        )
        if function is not None:
            workflow_name = function if isinstance(function, str) else function.name
        if workflow_name is None:
            raise ValueError("WorkflowDefinition needs a `function` (or `workflow_name`).")
        super().__init__(workflow_name=workflow_name, subject=subject, kwargs=kwargs)

    @property
    def function(self):
        from .models import Workflow

        return Workflow(name=self.workflow_name)


def __getattr__(name):
    # `WorkflowImplementation` used to be defined here. It is the Celery
    # engine's shim now, and importing it eagerly would be circular.
    if name == "WorkflowImplementation":
        from .celery.workflows import WorkflowImplementation

        return WorkflowImplementation
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
