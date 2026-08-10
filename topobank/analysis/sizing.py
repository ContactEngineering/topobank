"""
Predicting how much memory an analysis needs, so that one which cannot possibly
fit is refused up front instead of being discovered by the OOM killer.

Peak memory is close to linear in the number of grid points, with a coefficient
that is a property of the *workflow* rather than of the data. Measured on the
production instance: ``variable_bandwidth`` used 125.7 B/point on a
20178 x 20178 map and 128.8 B/point on an 8192 x 8192 one - 2.5% apart across a
sixfold change in size - and ``scale_dependent_curvature`` stayed within
746-830 B/point over eight different resolutions. So ``points x coefficient`` is
a usable predictor, which is the whole basis of this module.

The coefficient is *learned* from the ``task_memory`` column rather than written
down here. Every completed task records its own peak RSS (see
``taskapp/memory.py``), so no table of magic numbers has to be maintained and a
workflow that does not exist yet is covered the moment it has been run a few
times.

Only runs from the last ``TOPOBANK_ANALYSIS_MEMORY_WINDOW_DAYS`` days count, and
that window is what lets the coefficient come *down* again. Over an unbounded
history a high percentile is effectively immovable: with N old runs at the old
cost, an optimisation halving memory usage only moves a 95th percentile once the
improved runs outnumber the old ones nineteen to one. The guard would keep
predicting pre-optimisation memory for years and refuse analyses that now fit -
a false rejection, which is the direction that actually costs a user something.
With a window, the old runs age out and the coefficient follows the code. The
cost is that a workflow nobody has run inside the window has no coefficient at
all, which means the guard abstains: see below, that is the intended direction.

A high percentile plus a safety factor absorbs the spread within the window.
``autocorrelation``, for instance, ranges over 80-241 B/point, most likely
because FFT-based workflows pad non-power-of-two grids, though differing kwargs
would look the same in this data - runs are pooled per workflow, not per
argument set. Coefficients are derived from nominal (unpadded) point counts and
applied to nominal point counts, so padding ends up inside the coefficient
rather than having to be guessed per workflow.

**Everything here fails open.** No budget configured, no history for this
workflow, too few samples to trust, a subject whose size cannot be determined -
each of those lets the analysis run. The guard is here to stop the egregious
cases: a false rejection costs a user a result they could have had, while a
false acceptance costs no more than what already happens today.
"""

import logging
import math
from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import BigIntegerField, F, Max, Value
from django.db.models.functions import Cast, Coalesce
from django.template.defaultfilters import filesizeformat
from django.utils import timezone

from .exceptions import AnalysisTooLargeError

_log = logging.getLogger(__name__)

CACHE_KEY = "analysis-sizing-bytes-per-point"

#: Coefficients change only when an implementation changes, so this can be long.
CACHE_SECONDS = 3600

#: Percentile of the observed bytes-per-point distribution to predict with.
DEFAULT_PERCENTILE = 0.95

#: Multiplied onto the percentile, to leave room for the spread that a
#: percentile does not capture.
DEFAULT_SAFETY_FACTOR = 1.2

#: Below this many observations a workflow's coefficient is not trusted at all.
DEFAULT_MIN_SAMPLES = 5

#: How far back to look for observations. Long enough that ordinary workflows
#: keep a usable sample count, short enough that an optimisation is reflected
#: within a release cycle or two rather than never.
DEFAULT_WINDOW_DAYS = 90


def _setting(name, default):
    return getattr(settings, name, default)


def _percentile(values, fraction):
    """Nearest-rank percentile. Values must be non-empty."""
    ordered = sorted(values)
    rank = int(math.ceil(fraction * len(ordered)))
    return ordered[min(len(ordered) - 1, max(0, rank - 1))]


def _points_expression(prefix=""):
    """
    Grid points of a topography: line scans have no second dimension.

    The cast is not cosmetic. Both resolutions are 32-bit integers, and
    PostgreSQL multiplies ``integer * integer`` as an integer, so a map beyond
    roughly 46000 x 46000 would overflow the product - precisely the size of map
    this guard exists to catch.
    """
    return Cast(
        f"{prefix}resolution_x", BigIntegerField()
    ) * Coalesce(F(f"{prefix}resolution_y"), Value(1))


def observed_bytes_per_point(use_cache=True):
    """
    Learned memory coefficient per workflow, in bytes per grid point.

    Derived only from analyses of a single measurement, because that is the one
    case where the number of grid points involved is unambiguous, and only from
    runs inside the configured window, so that the coefficient can fall again
    when a workflow is optimised. A workflow with no recent runs is absent from
    the result, and callers must treat that as "no estimate".

    ``task_end_time`` dates a run rather than ``task_start_time``, because that
    is when its memory was measured. It is set on both the success and the
    failure path, so completed runs always carry one.
    """
    if use_cache:
        cached = cache.get(CACHE_KEY)
        if cached is not None:
            return cached

    from .models import WorkflowResult

    window_days = _setting("TOPOBANK_ANALYSIS_MEMORY_WINDOW_DAYS", DEFAULT_WINDOW_DAYS)
    rows = (
        WorkflowResult.objects.filter(
            task_memory__isnull=False,
            task_memory__gt=0,
            task_end_time__gte=timezone.now() - timedelta(days=window_days),
            subject_measurement__isnull=False,
            subject_measurement__resolution_x__isnull=False,
        )
        .annotate(points=_points_expression("subject_measurement__"))
        .values_list("workflow_name", "task_memory", "points")
    )

    ratios = defaultdict(list)
    for workflow_name, task_memory, points in rows.iterator():
        if points:
            ratios[workflow_name].append(task_memory / points)

    percentile = _setting("TOPOBANK_ANALYSIS_MEMORY_PERCENTILE", DEFAULT_PERCENTILE)
    min_samples = _setting("TOPOBANK_ANALYSIS_MEMORY_MIN_SAMPLES", DEFAULT_MIN_SAMPLES)
    coefficients = {
        name: _percentile(values, percentile)
        for name, values in ratios.items()
        if len(values) >= min_samples
    }
    cache.set(CACHE_KEY, coefficients, CACHE_SECONDS)
    return coefficients


def grid_points(analysis):
    """
    Grid points the workflow is expected to hold at once, or ``None``.

    For a subject that is a set of measurements this is the size of the *largest*
    one, not their sum: these workflows compute per measurement and combine the
    results, so the sum would overestimate badly and start rejecting legitimate
    work. Underestimating is the safe direction - it lets the analysis run, which
    is what happens today anyway.

    Tag subjects return ``None``. Resolving a tag to its measurements means
    walking the tag tree across both surfaces and measurements, and a guard that
    is wrong is worse than a guard that abstains.
    """
    from topobank.manager.models import Measurement

    if analysis.subject_measurement_id is not None:
        topography = analysis.subject_measurement
        if topography.resolution_x is None:
            return None
        return topography.resolution_x * (topography.resolution_y or 1)

    if analysis.subject_surface_id is not None:
        queryset = Measurement.objects.filter(surface_id=analysis.subject_surface_id)
    elif analysis.subject_tag_id is not None:
        return None
    else:
        surface_ids = list(analysis.surfaces.values_list("id", flat=True))
        if not surface_ids:
            return None
        queryset = Measurement.objects.filter(surface_id__in=surface_ids)

    return (
        queryset.filter(resolution_x__isnull=False)
        .annotate(points=_points_expression())
        .aggregate(largest=Max("points"))["largest"]
    )


def estimate_memory(analysis):
    """Predicted peak memory of this analysis in bytes, or ``None`` if unknown."""
    points = grid_points(analysis)
    if not points:
        return None

    coefficient = observed_bytes_per_point().get(analysis.workflow_name)
    if coefficient is None:
        return None

    safety_factor = _setting(
        "TOPOBANK_ANALYSIS_MEMORY_SAFETY_FACTOR", DEFAULT_SAFETY_FACTOR
    )
    return int(points * coefficient * safety_factor)


def check_memory_budget(analysis):
    """
    Raise ``AnalysisTooLargeError`` if this analysis cannot fit in memory.

    Returns the estimate (or ``None``) when the analysis may proceed, so callers
    can log it.
    """
    budget = _setting("TOPOBANK_ANALYSIS_MEMORY_BUDGET", None)
    if not budget:
        return None

    estimate = estimate_memory(analysis)
    if estimate is None:
        return None

    if estimate > budget:
        raise AnalysisTooLargeError(estimate, budget)

    _log.debug(
        "Analysis %s predicted to need %s of %s available.",
        analysis.id,
        filesizeformat(estimate),
        filesizeformat(budget),
    )
    return estimate
