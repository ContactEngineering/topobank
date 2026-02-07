"""
Registry for collection analysis functions.
"""

import logging

from rest_framework.exceptions import APIException

_log = logging.getLogger(__name__)


#
# Exceptions
#


class WorkflowRegistryException(APIException):
    """Generic exception for problems while handling analysis functions."""

    status_code = 400
    default_detail = "Bad workflow request."


class AlreadyRegisteredException(WorkflowRegistryException):
    """A function has already been registered for the given key."""

    def __init__(self, key):
        self._key = key

    def __str__(self):
        return f"An implementation for key '{self._key}' has already been defined."


class WorkflowNotImplementedException(WorkflowRegistryException):
    """An analysis function implementation was not found for given subject type."""

    def __init__(self, name, subject_model):
        self._name = name
        self._subject_model = subject_model

    def __str__(self):
        return (
            f"Workflow '{self._name}' has no implementation for subject "
            f"'{self._subject_model}'."
        )


class UnknownKeyException(WorkflowRegistryException):
    """A key was requested which is not known."""

    def __init__(self, key):
        self._key = key

    def __str__(self):
        return f"Key '{self._key}' is unknown."


#
# Handling of analysis function implementations
#

_implementation_classes_by_display_name = {}
# key: (name, subject_app_name, subject_model)
#      where
#      name: str, Unique function name,
#      subject_app_name: str, application name for subject_model
#      subject_model: str, e.g. "topography" or "surface",
#                     should correspond to first argument of analysis function implementations
#                     and to model class name
# value: reference to implementation of analysis function

_implementation_classes_by_name = {}
# key: (name, subject_app_name, subject_model)
#      where
#      name: str, Unique function name,
#      subject_app_name: str, application name for subject_model
#      subject_model: str, e.g. "topography" or "surface",
#                     should correspond to first argument of analysis function implementations
#                     and to model class name
# value: reference to implementation of analysis function

_app_name = {}
# key: visualization_type: str, visualization type
# value: Name of Django app/plugin where the visualization resides


def register_implementation(klass):
    """
    Register implementation of an analysis function.

    Parameters
    ----------
    klass: AnalysisImplementation
        Runner class that has the Python function which implements the analysis, and
        additional metadata

    Returns
    -------
    klass
        The registered class (to support use as a decorator)
    """
    _implementation_classes_by_display_name[klass.Meta.display_name] = klass
    _implementation_classes_by_name[klass.Meta.name] = klass
    return klass


def get_implementation(display_name=None, name=None):
    """
    Return WorkflowImplementation for given analysis function and subject type.

    Parameters
    ----------
    name : str
        Name of analysis function.

    Returns
    -------
    runner : AnalysisImplementation
        The analysis function
    """
    if display_name is not None:
        try:
            return _implementation_classes_by_display_name[display_name]
        except KeyError:
            return None
    elif name is not None:
        try:
            return _implementation_classes_by_name[name]
        except KeyError:
            return None
    else:
        raise RuntimeError("Please specify either `name` or `display_name`.")


def get_analysis_function_names(user=None):
    """
    Returns function names as list.

    If given a user, only the functions are returned
    which have at least one implementation for the given user.
    """
    runner_classes = _implementation_classes_by_name
    if user is not None:
        # filter for user
        runner_classes = {
            k: runner_class
            for k, runner_class in runner_classes.items()
            if runner_class.has_permission(user)
        }

    return list(runner_classes.keys())


def sync_implementation_classes(cleanup=False):
    """
    Make sure all analysis functions are represented in database.

    It's recommended to run this with cleanup=True if an analysis
    function should be removed.

    Parameters
    ----------

    cleanup: bool
        If True, delete all analysis functions for which no implementations exist
        and also delete all analyses related to those functions.
        Be careful, might delete existing analyses.
    """
    from .models import Workflow, WorkflowResult

    counts = dict(
        funcs_updated=0,
        funcs_created=0,
        funcs_deleted=0,
    )

    names_used = list(_implementation_classes_by_name.keys())

    #
    # Ensure all analysis functions needed to exist in database
    #
    _log.info(
        f"Syncing analysis functions with database - {len(names_used)} "
        "functions used - .."
    )

    for name in names_used:
        func, created = Workflow.objects.update_or_create(name=name)
        func.display_name = _implementation_classes_by_name[name].Meta.display_name
        func.save(update_fields=["display_name"])
        if created:
            counts["funcs_created"] += 1
        else:
            counts["funcs_updated"] += 1

    #
    # Optionally delete all analysis functions which are no longer needed
    #
    for func in Workflow.objects.all():
        if func.name not in names_used:
            _log.info(f"Function '{func.name}' is no longer used in the code.")
            dangling_analyses = WorkflowResult.objects.filter(function=func)
            num_analyses = dangling_analyses.filter(function=func).count()
            _log.info(f"There are still {num_analyses} analyses for this function.")
            if cleanup:
                _log.info("Deleting those...")
                dangling_analyses.delete()
                func.delete()
                _log.info(
                    f"Deleted function '{func.name}' and all its analyses."
                )
                counts["funcs_deleted"] += 1

    return counts
