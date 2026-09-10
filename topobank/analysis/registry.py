"""
Registry façade for workflows.

Workflows are registered with the workflow manager that runs them (see
:mod:`topobank.analysis.managers`); this module offers the historical
module-level functions over all configured managers, so callers that only need
"which workflows exist" or "give me the descriptor for this name" do not have
to know about managers.
"""

from .legacy.registry import (  # noqa: F401
    AlreadyRegisteredException,
    UnknownKeyException,
    WorkflowNotImplementedException,
    WorkflowRegistryException,
)
from .managers import get_workflow_names as _get_workflow_names
from .managers import resolve_workflow, resolve_workflow_by_display_name


def register_implementation(klass):
    """
    Register a `WorkflowImplementation` with the Celery workflow manager.

    Kept for plugins written before managers existed; new code registers with
    the manager it targets, e.g. ``topobank.analysis.celery_manager.registry``.
    """
    from .celery_manager import registry

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
