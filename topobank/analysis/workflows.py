"""
Implementations of analysis functions for topographies and surfaces.

The first argument is either a Topography or Surface instance (model).
"""

import collections
import logging
from dataclasses import dataclass
from typing import Union

import numpy as np
import pydantic
from django.conf import settings

from ..manager.models import Surface, Topography
from ..supplib.dict import SplitDictionaryHere
from .models import Workflow
from .registry import WorkflowNotImplementedException

_log = logging.getLogger(__name__)

# Visualization types
APP_NAME = "analysis"
VIZ_SERIES = "series"


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
        class Config:
            extra = "forbid"

    def __init__(self, **kwargs):
        self._kwargs = self.Parameters(**kwargs)

    @property
    def kwargs(self):
        return self._kwargs

    def eval(self, analysis, **auxiliary_kwargs):
        implementation = self.get_implementation(analysis.subject.__class__)
        return implementation(analysis, **auxiliary_kwargs)

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

        try:
            dependency_func = getattr(self, dependencies[analysis.subject.__class__])
            _log.debug("Dependency function exists.")
        except KeyError:
            _log.debug(f"No dependency function for subject {analysis.subject} found.")
            dependencies = []
        else:
            dependencies = dependency_func(analysis)
        return dependencies

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

    @classmethod
    def has_permission(cls, user: settings.AUTH_USER_MODEL):
        """Return whether this implementation is available for the given user."""
        if cls.__module__.startswith("topobank.testing."):
            return True

        app = cls._get_app_config_for_obj(cls)

        if app is None:
            return False
        elif (
            hasattr(app, "TopobankPluginMeta") and not app.TopobankPluginMeta.restricted
        ):
            # This plugin is marked as being available to everyone
            return True

        from ..organizations.models import Organization

        plugins_available = Organization.objects.get_plugins_available(user)
        return app.name in plugins_available
