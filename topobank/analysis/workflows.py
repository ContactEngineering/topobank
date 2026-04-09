"""
Implementations of analysis functions for topographies and surfaces.

The first argument is either a Topography or Surface instance (model).
"""

import collections
import hashlib
import logging
import warnings
from dataclasses import dataclass
from typing import Union

import numpy as np
import pydantic
from pydantic import field_validator

from ..manager.models import Surface, Tag, Topography
from ..supplib.dict import SplitDictionaryHere
from .models import Workflow
from .outputs import get_outputs_schema
from .registry import WorkflowNotImplementedException

_log = logging.getLogger(__name__)

# Visualization types
APP_NAME = "analysis"
VIZ_SERIES = "series"


def compute_surfaces_hash(surface_ids):
    """Compute a deterministic hash for a set of surface IDs."""
    sorted_ids = sorted(set(surface_ids))
    key = ",".join(str(sid) for sid in sorted_ids)
    return hashlib.sha256(key.encode()).hexdigest()


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
    def surfaces_hash(self) -> str:
        return compute_surfaces_hash(self.surfaces)


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
        wrapped_series.append(
            SplitDictionaryHere(f"series-{i}", s, supplementary=supplementary)
        )
    return wrapped_series


def make_alert_entry(level, subject_name, subject_url, data_series_name, detail_mesg):
    """Build string with alert message often used in the functions.

    Parameters
    ----------
    level: str
        One of ['info', 'warning', 'danger'], see also alert classes in bootstrap 4
    subject_name: str
        Name of the subject.
    subject_url: str
        URL of the subject
    data_series_name: str
        Name of the data series this applies to.
    detail_mesg: str
        Details about the alert.

    Returns
    -------
    str
    """
    link = f'<a class="alert-link" href="{subject_url}">{subject_name}</a>'
    message = f"Failure for digital surface twin {link}, data series '{data_series_name}': {detail_mesg}"
    return dict(alert_class=f"alert-{level}", message=message)


@dataclass
class WorkflowDefinition:
    # We don't allow tags as dependencies
    subject: Union[Surface, Topography] = None

    # Analysis function
    function: Workflow = None

    # Parameters
    kwargs: dict = None


class WorkflowImplementation:
    """Class that holds the actual implementation of a workflow"""

    class Meta:
        celery_queue = None
        implementations = {}
        dependencies = {}

    class Parameters(pydantic.BaseModel):
        model_config = pydantic.ConfigDict(extra="forbid")

    # Optional outputs declaration - subclasses can define an Outputs class
    Outputs = None

    def __init__(self, **kwargs):
        self._kwargs = self.Parameters(**kwargs)

    @property
    def kwargs(self):
        return self._kwargs

    def eval(self, analysis, **auxiliary_kwargs):
        if analysis.subject is None and analysis.surfaces.exists():
            return self.eval_surfaces(analysis, **auxiliary_kwargs)
        implementation = self.get_implementation(analysis.subject.__class__)
        result = implementation(analysis, **auxiliary_kwargs)
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

        result = impl(analysis, **auxiliary_kwargs)
        if result is not None:
            warnings.warn(
                f"Workflow implementation '{self.Meta.name}' returned a result of type {type(result)}. "
                f"Returning results from workflows is deprecated. Please store results as files instead.",
                DeprecationWarning,
            )
        return result

    @classmethod
    def clean_kwargs(cls, kwargs: Union[dict, None], fill_missing: bool = True):
        """
        Validate keyword arguments (parameters) and return validated dictionary

        Parameters
        ----------
        kwargs: Union[dict, None]
            Keyword arguments
        fill_missing: bool, optional
            Fill missing keys with default values. (Default: True)

        Raises
        ------
        pydantic.ValidationError if validation fails
        """
        if kwargs is None:
            if fill_missing:
                return cls.Parameters().model_dump()
            else:
                return {}
        else:
            return cls.Parameters(**kwargs).model_dump(exclude_unset=not fill_missing)

    @classmethod
    def get_outputs_schema(cls) -> list:
        """
        Get JSON schema for declared outputs.

        Returns
        -------
        list
            List of file descriptors with their schemas
        """
        return get_outputs_schema(getattr(cls, "Outputs", None))

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
        """Route dependency resolution based on surface set size.

        Parameters
        ----------
        analysis : WorkflowResult
            The analysis instance for which dependencies are being resolved.
        dependencies : dict
            Dictionary mapping subject models to their dependency functions.

        Returns
        -------
        list
            List of dependencies for the given analysis.
        """
        surfaces = list(analysis.surfaces.all())
        n = len(surfaces)

        # If we have more than one surface, we use the Tag-based dependency function if it exists.
        if n > 1:
            dep_key = Tag
        # If we have exactly one surface, we check for a Surface-based dependency function first,
        # then fall back to a Topography-based one if it doesn't exist.
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

        # Call the dependency function and return its result
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
        # FIXME: `app` should not be None, except in certain supplib. Can we add some form of guard here?
        # if app is None:
        #    raise RuntimeError(f'Could not find app config for {obj.__module__}. Is the Django app installed and '
        #                       f'registered? This is likely a misconfigured Django installation.')
        return app
