"""
Registry for analysis functions.

Legacy WorkflowImplementation registration lives in topobank.analysis.legacy.registry.
This module re-exports legacy symbols for backwards compatibility and provides
the muFlow-aware lookup functions used by the rest of the analysis system.
"""

import logging

from muflow import registry as muflow_registry

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
from .muflow.adapter import MuFlowWorkflowAdapter

_log = logging.getLogger(__name__)


def get_implementation(display_name=None, name=None):
    """
    Return WorkflowImplementation for given analysis function and subject type.

    This function first checks the muFlow registry for matching workflows,
    then falls back to the legacy topobank registry.

    Parameters
    ----------
    display_name : str, optional
        Display name of analysis function.
    name : str, optional
        Internal name of analysis function.

    Returns
    -------
    runner : WorkflowImplementation or MuFlowWorkflowAdapter
        The analysis function implementation.
    """
    # Try muFlow registry first
    try:
        entry = None
        if name:
            entry = muflow_registry.get(name)
        if not entry and display_name:
            entry = muflow_registry.get_by_display_name(display_name)
        if entry:
            _log.debug(f"Found muFlow workflow for '{name or display_name}'")
            return MuFlowWorkflowAdapter(entry)
    except ImportError:
        pass
    except Exception as e:
        _log.warning(f"Error checking muFlow registry: {e}")

    # Fall back to legacy registry
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

    The `user` parameter is deprecated and ignored.
    """
    names = list(_implementation_classes_by_name.keys())
    try:
        for name in muflow_registry.get_all().keys():
            if name not in names:
                names.append(name)
    except Exception as e:
        _log.warning(f"Error fetching muFlow workflows: {e}")
    return names


def sync_implementation_classes(cleanup=False):
    """
    No-op kept for backwards compatibility.

    The Workflow database model has been removed. Workflow metadata is now
    derived from the registry at runtime. This function previously synced the
    registry to the database but is now a no-op.
    """
    _log.debug(
        "sync_implementation_classes called — no-op since Workflow DB model was removed."
    )
    return dict(funcs_updated=0, funcs_created=0, funcs_deleted=0)
