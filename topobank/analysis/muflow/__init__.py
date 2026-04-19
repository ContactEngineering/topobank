"""
muFlow integration for topobank's analysis system.

This package provides the bridge layer that:
1. Wraps muFlow TaskEntry objects as WorkflowImplementation-like adapters
2. Converts Django models (Tag, Surface) to muFlow's DatasetInfo schema
3. Handles completion callbacks to sync muFlow results with topobank
"""

from .adapter import MuFlowWorkflowAdapter

__all__ = ["MuFlowWorkflowAdapter"]
