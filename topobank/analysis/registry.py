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
    try:
        for name, entry in muflow_registry.get_all().items():
            if name not in names_used:
                names_used.append(name)
    except Exception as e:
        _log.warning(f"Error fetching muFlow workflows: {e}")

    #
    # Ensure all analysis functions needed to exist in database
    #
    _log.info(
        f"Syncing analysis functions with database - {len(names_used)} "
        "functions used - .."
    )

    for name in names_used:
        func, created = Workflow.objects.update_or_create(name=name)
        if name in _implementation_classes_by_name:
            func.display_name = _implementation_classes_by_name[name].Meta.display_name
        else:
            entry = muflow_registry.get(name)
            if entry:
                func.display_name = getattr(entry, "display_name", entry.name)
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
