"""
Implementations of analysis functions for topographies and surfaces.

The first argument is either a Topography or Surface instance (model).
"""

import collections
import logging

import numpy as np

from ..utils import SplitDictionaryHere

_log = logging.getLogger(__name__)

# Visualization types
APP_NAME = 'analysis'
VIZ_GENERIC = 'generic'
VIZ_SERIES = 'series'


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
        return int(np.sqrt(np.prod(len(topography.positions()))) + 1.0)  # TODO discuss whether auto or this
        # return 'auto'


class IncompatibleTopographyException(Exception):
    """Raise this exception in case a function cannot handle a topography.

    By handling this special exception, the UI can show the incompatibility
    as note to the user, not as failure. It is an excepted failure.
    """
    pass


class ReentrantTopographyException(IncompatibleTopographyException):
    """Raise this exception if a function cannot handle a topography because it is reentrant.

    By handling this special exception, the UI can show the incompatibility
    as note to the user, not as failure. It is an excepted failure.
    """
    pass


def wrap_series(series, primary_key='x'):
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
        supplementary = {'name': s['name'], 'nbDataPoints': len(s[primary_key])}
        if 'visible' in s:
            supplementary['visible'] = s['visible']
        wrapped_series.append(SplitDictionaryHere(
            f'series-{i}', s,
            supplementary=supplementary))
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


# This function will be registered in tests by a fixture
def topography_analysis_function_for_tests(topography, a=1, b="foo", progress_recorder=None, storage_prefix=None):
    """This function can be registered for tests.

    The arguments have no meaning. Result are two series.
    """
    return {'name': 'Test result for test function called for topography {}.'.format(topography),
            'xunit': 'm',
            'yunit': 'm',
            'xlabel': 'x',
            'ylabel': 'y',
            'series': [
                dict(
                    name='Fibonacci series',
                    x=np.array((1, 2, 3, 4, 5, 6, 7, 8)),
                    y=np.array((0, 1, 1, 2, 3, 5, 8, 13)),
                    std_err_y=np.zeros(8),
                ),
                dict(
                    name='Geometric series',
                    x=np.array((1, 2, 3, 4, 5, 6, 7, 8)),
                    y=0.5 ** np.array((1, 2, 3, 4, 5, 6, 7, 8)),
                    std_err_y=np.zeros(8),
                ),
            ],
            'alerts': [dict(alert_class='alert-info', message="This is a test for a measurement alert.")],
            'comment': f"Arguments: a is {a} and b is {b}"}


# This function will be registered in tests by a fixture
def surface_analysis_function_for_tests(surface, a=1, b="foo", progress_recorder=None, storage_prefix=None):
    """This function can be registered for tests."""
    return {'name': 'Test result for test function called for surface {}.'.format(surface),
            'xunit': 'm',
            'yunit': 'm',
            'xlabel': 'x',
            'ylabel': 'y',
            'series': [],
            'alerts': [dict(alert_class='alert-info', message="This is a test for a surface alert.")],
            'comment': f"a is {a} and b is {b}"}


# This function will be registered in tests by a fixture
def tag_analysis_function_for_tests(tag, a=1, b="foo", progress_recorder=None, storage_prefix=None):
    """This function can be registered for tests.

    Parameters
    ----------
    tag : Tag
        Analysis subject.
    a: int
        Just a parameter as example.
    d: str
        Another example parameter.
    progress_recorder: ProgressRecorder instance
        If given, a progress recorder used as callback for reporting progress to
        user interface.
    storage_prefix: str or None
        If given, prefix for files in storage which should be used to store
        files related to this analysis.
    """

    name = f'Test result for test function called for tag {tag}, ' \
           ', which is built from surfaces {}'.format([s.name for s in tag.surface_set.all()])

    return {'name': name,
            'xunit': 'm',
            'yunit': 'm',
            'xlabel': 'x',
            'ylabel': 'y',
            'series': [],
            'alerts': [dict(alert_class='alert-info', message="This is a test for an alert.")],
            'comment': f"a is {a} and b is {b}"}
