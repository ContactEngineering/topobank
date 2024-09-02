"""
Implementations of analysis functions for topographies and surfaces.

The first argument is either a Topography or Surface instance (model).
"""

import collections
import logging
from typing import Union

import numpy as np
import pydantic
from django.conf import settings
from django.core.files.base import ContentFile

from ..files.models import Folder
from ..manager.models import Surface, Tag, Topography
from ..supplib.dict import SplitDictionaryHere
from .registry import ImplementationMissingAnalysisFunctionException

_log = logging.getLogger(__name__)

# Visualization types
APP_NAME = "analysis"
VIZ_GENERIC = "generic"
VIZ_SERIES = "series"


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


class AnalysisImplementation:
    """Class that holds the actual implementation of an analysis function"""

    class Meta:
        implementations = {}

    class Parameters(pydantic.BaseModel):
        class Config:
            extra = "forbid"

    def __init__(self, kwargs: Union[dict, None]):
        if kwargs:
            self._kwargs = self.Parameters(**kwargs)
        else:
            # Use default parameters
            self._kwargs = self.Parameters()

    def eval(self, subject, folder, progress_recorder):
        implementation = self.get_implementation_for_subject(subject.__class__)
        return implementation(subject, folder, progress_recorder=progress_recorder)

    @classmethod
    def clean_kwargs(cls, kwargs: Union[dict, None]):
        """
        Validate keyword arguments (parameters) and return validated dictionary

        Raises
        ------
        pydantic.ValidationError if validation fails
        """
        if kwargs is None:
            return cls.Parameters().model_dump()
        else:
            return cls.Parameters(**kwargs).model_dump()

    def get_dependent_analyses(self):
        return []  # Default is no dependencies

    def get_implementation_for_subject(self, model):
        """Returns the implementation function for a specific subject model"""
        try:
            name = self.Meta.implementations[model]
        except KeyError:
            raise ImplementationMissingAnalysisFunctionException(self.Meta.name, model)
        return getattr(self, name)

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

        app = cls._get_app_config_for_obj(cls)

        if app is None:
            return False
        elif (
            app.name == "topobank.analysis"
        ):  # special case, should be always available
            return True
        elif (
            hasattr(app, "TopobankPluginMeta") and not app.TopobankPluginMeta.restricted
        ):
            # This plugin is marked as being available to everyone
            return True

        from ..organizations.models import Organization

        plugins_available = Organization.objects.get_plugins_available(user)
        return app.name in plugins_available


class TestImplementation(AnalysisImplementation):
    """
    This function will be registered in conftest.py by a fixture. The arguments have no
    meaning. Result are two series.
    """

    class Meta:
        name = "test"
        visualization_app_name = "analysis"
        visualization_type = VIZ_SERIES

        implementations = {
            Topography: "topography_implementation",
            Surface: "surface_implementation",
            Tag: "tag_implementation",
        }

    class Parameters(AnalysisImplementation.Parameters):
        a: int = 1
        b: str = "foo"

    def topography_implementation(
        self, topography: Topography, folder: Folder, progress_recorder=None
    ):
        folder.save_file("test.txt", "der", ContentFile("Test!!!"))
        return {
            "name": "Test result for test function called for topography "
            f"{topography}.",
            "xunit": "m",
            "yunit": "m",
            "xlabel": "x",
            "ylabel": "y",
            "series": [
                dict(
                    name="Fibonacci series",
                    x=np.array((1, 2, 3, 4, 5, 6, 7, 8)),
                    y=np.array((0, 1, 1, 2, 3, 5, 8, 13)),
                    std_err_y=np.zeros(8),
                ),
                dict(
                    name="Geometric series",
                    x=np.array((1, 2, 3, 4, 5, 6, 7, 8)),
                    y=0.5 ** np.array((1, 2, 3, 4, 5, 6, 7, 8)),
                    std_err_y=np.zeros(8),
                ),
            ],
            "alerts": [
                dict(
                    alert_class="alert-info",
                    message="This is a test for a measurement alert.",
                )
            ],
            "comment": f"Arguments: a is {self._kwargs.a} and b is "
            f"{self._kwargs.b}",
        }

    def surface_implementation(
        self, surface: Surface, folder: Folder, progress_recorder=None
    ):
        """This function can be registered for supplib."""
        return {
            "name": "Test result for test function called for surface {}.".format(
                surface
            ),
            "xunit": "m",
            "yunit": "m",
            "xlabel": "x",
            "ylabel": "y",
            "series": [],
            "alerts": [
                dict(
                    alert_class="alert-info",
                    message="This is a test for a surface alert.",
                )
            ],
            "comment": f"a is {self._kwargs.a} and b is {self._kwargs.b}",
        }

    def tag_implementation(self, tag: Tag, folder: Folder, progress_recorder=None):
        name = (
            f"Test result for test function called for tag {tag}, "
            ", which is built from surfaces {}".format(
                [s.name for s in tag.surface_set.all()]
            )
        )

        return {
            "name": name,
            "xunit": "m",
            "yunit": "m",
            "xlabel": "x",
            "ylabel": "y",
            "series": [],
            "alerts": [
                dict(alert_class="alert-info", message="This is a test for an alert.")
            ],
            "surfaces": [surface.name for surface in tag.get_related_surfaces()],
            "comment": f"a is {self._kwargs.a} and b is {self._kwargs.b}",
        }


class SecondTestImplementation(AnalysisImplementation):
    """
    This function will be registered in conftest.py by a fixture. The arguments have no
    meaning. Result are two series.
    """

    class Meta:
        name = "test2"
        visualization_app_name = "analysis"
        visualization_type = VIZ_SERIES

        implementations = {
            Topography: "topography_implementation",
        }

    class Parameters(AnalysisImplementation.Parameters):
        c: int = 1
        d: float = 1.3

    def get_dependent_analyses(self):
        pass

    def topography_implementation(
        self, topography: Topography, folder: Folder, progress_recorder=None
    ):
        return {
            "name": "Test with dependencies"
        }
