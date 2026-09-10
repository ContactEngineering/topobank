"""
Registry façade for workflows.

Workflows are registered with the workflow manager that runs them (see
:mod:`topobank.analysis.managers`); this module offers the historical
module-level functions over all configured managers, so callers that only need
"which workflows exist" or "give me the descriptor for this name" do not have
to know about managers.
"""

from .managers import get_workflow_names as _get_workflow_names
from .managers import resolve_workflow, resolve_workflow_by_display_name

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
# Façade
#


def register_implementation(klass):
    """
    Register a `WorkflowImplementation` with the Celery workflow manager.

    Kept for plugins written before managers existed; new code registers with
    the manager it targets, e.g. ``topobank.analysis.celery.manager.registry``.
    """
    from .celery.manager import registry

    return registry.register(klass)


def get_implementation(display_name=None, name=None):
    """Return the descriptor (shim) class registered for a workflow, or None."""
    if display_name is not None:
        resolved = resolve_workflow_by_display_name(display_name)
    elif name is not None:
        resolved = resolve_workflow(name)
    else:
        raise RuntimeError("Please specify either `name` or `display_name`.")
    return None if resolved is None else resolved[1]


def get_workflow_names(user=None):
    """Returns registered workflow names. The `user` parameter is deprecated."""
    return _get_workflow_names()
