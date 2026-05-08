"""
Registry for analysis functions.
"""

from .legacy.registry import (  # noqa: F401
    AlreadyRegisteredException,
    UnknownKeyException,
    WorkflowNotImplementedException,
    WorkflowRegistryException,
    _app_name,
    _implementation_classes_by_display_name,
    _implementation_classes_by_name,
    register_implementation,
)


def get_implementation(display_name=None, name=None):
    """Return WorkflowImplementation for given analysis function."""
    if display_name is not None:
        return _implementation_classes_by_display_name.get(display_name)
    elif name is not None:
        return _implementation_classes_by_name.get(name)
    else:
        raise RuntimeError("Please specify either `name` or `display_name`.")


def get_analysis_function_names(user=None):
    """Returns registered function names. The `user` parameter is deprecated."""
    return list(_implementation_classes_by_name.keys())
