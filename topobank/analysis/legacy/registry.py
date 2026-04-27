"""
Legacy registry for WorkflowImplementation-based analysis functions.

New workflows should use muFlow's @register_task decorator instead.
"""


#
# Exceptions
#


class WorkflowRegistryException(Exception):
    """Generic exception for problems while handling analysis functions."""


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
# Legacy registry dicts
#

_implementation_classes_by_display_name = {}
_implementation_classes_by_name = {}
_app_name = {}


def register_implementation(klass):
    """
    Register implementation of an analysis function.

    Parameters
    ----------
    klass: WorkflowImplementation
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
