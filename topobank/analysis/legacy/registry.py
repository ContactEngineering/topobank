"""
Exceptions of the workflow registry, and the historical registration entry point.
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


def register_implementation(klass):
    """
    Register a `WorkflowImplementation` with the Celery workflow manager.

    Historical entry point; see `topobank.analysis.registry.register_implementation`.
    """
    from ..celery_manager import registry

    return registry.register(klass)
