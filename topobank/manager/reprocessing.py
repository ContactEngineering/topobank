"""Finding measurements whose derived files are out of date.

A measurement's derived files are out of date when a processing step the
deployment runs (``TOPOBANK_PROCESSING_STEPS``) applies to its kind but its files
were not written by the step's current version (with the current options), see
`ProcessingStepRecord`. That is the case after a step's version is bumped, its
options changed, or a step added: e.g. a deployment that adds a mesh-map step
gets mesh maps for every measurement uploaded before.

Measurements that were inspected before kinds were recorded, and whose kind
could not be told from their columns, count as out of date too.
"""

from django.conf import settings
from django.db.models import Exists, OuterRef, Q

from ..settings import defaults
from .kinds import get_adapters
from .models import ProcessingStepRecord, Topography
from .steps import resolve_steps, step_version


def configured_steps():
    """The deployment's processing steps, with the version each records."""
    specs = getattr(
        settings, "TOPOBANK_PROCESSING_STEPS", defaults.TOPOBANK_PROCESSING_STEPS
    )
    options = getattr(
        settings,
        "TOPOBANK_PROCESSING_STEP_OPTIONS",
        defaults.TOPOBANK_PROCESSING_STEP_OPTIONS,
    )
    return [
        (step, step_version(step, options.get(step.name)))
        for step in resolve_steps(specs)
    ]


def outdated_topographies(retry_failed=False):
    """The measurements whose derived files are out of date.

    Only measurements with complete metadata count: the others have no derived
    files at all until the user completes it. A step that failed with its current
    version counts as up to date, unless `retry_failed`.
    """
    queryset = Topography.objects.filter(
        resolution_x__isnull=False, size_x__isnull=False, unit__isnull=False
    )
    adapters = get_adapters()
    outdated = Q(kind__isnull=True)
    for step, version in configured_steps():
        kinds = [kind for kind, adapter in adapters.items() if step.applies_to(adapter)]
        if not kinds:
            continue
        current = ProcessingStepRecord.objects.filter(
            topography=OuterRef("pk"), name=step.name, version=version
        )
        if retry_failed:
            current = current.filter(succeeded=True)
        outdated |= Q(kind__in=kinds) & ~Exists(current)
    return queryset.filter(outdated)
