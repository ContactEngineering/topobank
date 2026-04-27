"""
Implementations of analysis functions for topographies and surfaces.

Legacy workflow code lives in topobank.analysis.legacy.workflows.
This module re-exports everything for backwards compatibility.
"""

from .legacy.workflows import (  # noqa: F401
    ContainerProxy,
    WorkflowDefinition,
    WorkflowError,
    WorkflowImplementation,
    make_alert_entry,
    reasonable_bins_argument,
    wrap_series,
)

# Visualization types (kept here as they are analysis-module constants)
APP_NAME = "analysis"
VIZ_SERIES = "series"
