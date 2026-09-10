"""
Building blocks shared by workflows and the code that submits them.

Nothing in this module runs a workflow or knows how one is run. It holds what
every workflow manager and every shim has in common: how a set of surfaces is
identified (`SurfaceSet`, `compute_subject_hash`), how a workflow declares a
dependency (`WorkflowDefinition`), and helpers that implementations use to
build their results (`ContainerProxy`, `wrap_series`, `make_alert_entry`,
`reasonable_bins_argument`).

The Celery manager's shim, `WorkflowImplementation`, lives in
:mod:`topobank.analysis.celery.workflows`; it is still importable from here for
callers written before workflow managers existed.
"""

import collections
import hashlib
import logging
from dataclasses import dataclass
from typing import Union

import numpy as np
import pydantic
from pydantic import field_validator

from ..manager.models import Surface, Topography
from ..supplib.dict import SplitDictionaryHere
from .models import Workflow

_log = logging.getLogger(__name__)

APP_NAME = "analysis"
VIZ_SERIES = "series"


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
class WorkflowDefinition:
    # We don't allow tags as dependencies
    subject: Union[Surface, Topography] = None

    # Analysis function
    function: Workflow = None

    # Parameters
    kwargs: dict = None


def __getattr__(name):
    # `WorkflowImplementation` used to be defined here. It is the Celery
    # manager's shim now, and importing it eagerly would be circular.
    if name == "WorkflowImplementation":
        from .celery.workflows import WorkflowImplementation

        return WorkflowImplementation
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
