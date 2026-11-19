"""System checks of the analysis app's settings."""

from django.conf import settings
from django.core.checks import Error, register
from django.utils.module_loading import import_string

from ..settings import defaults


@register()
def check_workflow_dispatcher(app_configs, **kwargs):
    """`TOPOBANK_WORKFLOW_DISPATCHER` names a callable that can be imported,
    so a typo fails a deploy's `migrate` rather than every submission."""
    path = getattr(
        settings, "TOPOBANK_WORKFLOW_DISPATCHER", defaults.TOPOBANK_WORKFLOW_DISPATCHER
    )
    if not path:
        return []
    try:
        dispatcher = import_string(path)
    except ImportError as exc:
        return [
            Error(
                f"TOPOBANK_WORKFLOW_DISPATCHER {path!r} cannot be imported: {exc}",
                id="topobank.analysis.E001",
            )
        ]
    if not callable(dispatcher):
        return [
            Error(
                f"TOPOBANK_WORKFLOW_DISPATCHER {path!r} is not callable",
                id="topobank.analysis.E002",
            )
        ]
    return []
