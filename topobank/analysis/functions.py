"""
Implementations of analysis functions for topographies and surfaces.

The first argument is either a Topography or Surface instance (model).
"""

import collections
import logging

import numpy as np
import pydantic
from django.conf import settings

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


#
# Use this during development if you need a long running task with failures
#
# @register_implementation(ART_GENERIC, 'long')
# def long_running_task(topography, progress_recorder=None, storage_prefix=None):
#     topography = topography.topography()
#     import time, random
#     n = 10 + random.randint(1,10)
#     F = 30
#     for i in range(n):
#         time.sleep(0.5)
#         if random.randint(1, F) == 1:
#             raise ValueError("This error is intended and happens with probability 1/{}.".format(F))
#         progress_recorder.set_progress(i+1, n)
#     return dict(message="done", physical_sizes=topography.physical_sizes, n=n)


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


class AnalysisRunner:
    """Class that holds the actual implementation of an analysis function"""

    class Meta:
        runners = {}

    class Parameters(pydantic.BaseModel):
        pass

    def __init__(self, parameters: dict):
        self._parameters = self.Parameters(**parameters)

    def eval(self, subject, progress_recorder, storage_prefix):
        runner = self.get_runner(subject.__class__)
        return runner(
            subject, progress_recorder=progress_recorder, storage_prefix=storage_prefix
        )

    @classmethod
    def validate(cls, parameters):
        cls.Parameters(**parameters)

    def get_dependent_analyses(self):
        return []  # Default is no dependencies

    def run_analysis(self, *args, **kwargs):
        raise NotImplementedError

    def get_runner(self, model):
        try:
            name = self.Meta.runners[model]
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


class TestRunner(AnalysisRunner):
    """
    This function will be registered in conftest.py by a fixture. The arguments have no
    meaning. Result are two series.
    """

    class Meta:
        name = "test"
        visualization_app_name = "analysis"
        visualization_type = VIZ_SERIES

        runners = {
            Topography: "topography_runner",
            Surface: "surface_runner",
            Tag: "tag_runner",
        }

    class Parameters(pydantic.BaseModel):
        a: int = 1
        b: str = "foo"

    def topography_runner(
        self, topography: Topography, progress_recorder=None, storage_prefix=None
    ):
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
            "comment": f"Arguments: a is {self._parameters.a} and b is "
            f"{self._parameters.b}",
        }

    def surface_runner(
        self,
        surface: Surface,
        progress_recorder=None,
        storage_prefix=None,
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
            "comment": f"a is {self._parameters.a} and b is {self._parameters.b}",
        }

    def tag_runner(self, tag: Tag, progress_recorder=None, storage_prefix=None):
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
            "comment": f"a is {self._parameters.a} and b is {self._parameters.b}",
        }
