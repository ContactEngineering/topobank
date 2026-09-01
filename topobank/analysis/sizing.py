"""
Predicting how much memory an analysis needs, so that one which cannot possibly
fit is refused up front instead of being discovered by the OOM killer.

Peak memory is a fixed process baseline plus a term close to linear in the
number of data points, with a coefficient that is a property of the *workflow*
rather than of the data. Measured on the production instance:
``variable_bandwidth`` used 125.7 B/point on a 20178 x 20178 map and
128.8 B/point on an 8192 x 8192 one - 2.5% apart across a sixfold change in
size - and ``scale_dependent_curvature`` stayed within 746-830 B/point over
eight different resolutions. So ``baseline + points x coefficient`` is a usable
predictor, which is the whole basis of this module.

How many data points a measurement holds is a property of its *kind*, so the
equations live on the measurement adapters (``nb_data_points`` for a single
instance, ``nb_data_points_expression`` for the SQL aggregates) and this module
only dispatches. A kind that does not implement them - a plugin's kind, or one
whose notion of size is not settled - simply is not sized, and the guard fails
open for it.

The coefficient is *learned* from the ``task_memory`` column rather than written
down here. Every completed task records its own peak RSS (see
``taskapp/memory.py``), so no table of magic numbers has to be maintained and a
workflow that does not exist yet is covered the moment it has been run a few
times.

The baseline is why small runs must not teach. ``task_memory`` is peak RSS, and
several hundred MB of that is interpreter, Django and numpy - resident before
the first data point is loaded. Dividing raw peak RSS by the subject's points
therefore does not converge to the workflow's coefficient for small subjects; it
diverges to ``baseline / points``. A power-spectrum run on a line scan of a few
hundred points yields *megabytes* per point, the high percentile below latches
onto exactly those samples, and every following analysis of that workflow is
refused no matter its size (issue #1393 - the production instance rejected
ordinary sub-megapixel maps with TB-scale predictions). Two measures keep the
baseline out of the coefficient: the assumed baseline is subtracted before
dividing (and added back when predicting), and runs on subjects below a minimum
point count are not used for learning at all, which bounds what an error in the
assumed baseline can contribute.

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

import pydantic
from django.conf import settings
from django.core.cache import cache
from django.db import DataError, transaction
from django.db.models import BigIntegerField, Case, Max, When
from django.template.defaultfilters import filesizeformat
from django.utils import timezone

from ..measurements.registry import get_adapter, get_adapters, has_adapter
from .exceptions import AnalysisTooLargeError

_log = logging.getLogger(__name__)

#: The version suffix is part of the coefficient semantics: coefficients
#: learned before the baseline subtraction (and before line scans counted
#: their positions) must not survive a deployment in a persistent cache --
#: they are exactly the poisoned values #1393 is about. Bump it whenever the
#: learning arithmetic changes.
CACHE_KEY = "analysis-sizing-bytes-per-point-v2"

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

#: Fixed per-process overhead assumed to be part of every recorded peak RSS:
#: interpreter, Django and the scientific libraries are resident before the
#: first data point is loaded. Subtracted before learning a coefficient, added
#: back when predicting. Production worker children have been observed at
#: roughly 300-700 MB before touching data, so this sits in the middle.
DEFAULT_BASELINE = 512 * 1024**2

#: Runs on subjects smaller than this teach us nothing about the per-point
#: cost: their peak RSS is almost entirely baseline. The subtraction above
#: removes the *assumed* baseline; this floor bounds what the remaining error
#: can contribute. 16 Mpoints is a 4096 x 4096 map, so an assumed baseline
#: that is off by even 512 MB contaminates a learned coefficient by at most
#: 32 B/point - small against every coefficient observed in practice.
DEFAULT_MIN_POINTS = 16 * 1024**2


def _setting(name, default):
    return getattr(settings, name, default)


def _percentile(values, fraction):
    """Nearest-rank percentile. Values must be non-empty."""
    ordered = sorted(values)
    rank = int(math.ceil(fraction * len(ordered)))
    return ordered[min(len(ordered) - 1, max(0, rank - 1))]


def _points_expression(prefix=""):
    """
    Datums of a measurement, dispatching on its kind, or ``None``.

    How many datums a measurement holds is a property of its kind, so the
    equation lives on the adapter (``nb_data_points_expression``) and this
    merely assembles the registered ones into a ``CASE`` over the ``kind``
    column. Every row therefore gets the equation of *its own* kind -- a
    dataset mixing maps and line scans sizes each measurement correctly, where
    a single shared equation would apply the wrong one to somebody.

    Rows no branch covers fall through to NULL: a kind that abstains, a kind
    whose plugin is not installed, and never-inspected measurements
    (``kind IS NULL`` matches no ``When``). NULL is skipped by ``Max`` and by
    the coefficient learner, so an unsizable measurement counts as unknown
    rather than as 0. ``None`` is returned when no registered kind supplies an
    expression at all, and callers abstain.
    """
    whens = [
        When(**{f"{prefix}kind": kind}, then=expression)
        for kind, adapter in get_adapters().items()
        if (expression := adapter.nb_data_points_expression(prefix)) is not None
    ]
    if not whens:
        return None
    return Case(*whens, default=None, output_field=BigIntegerField())


def points_in_sql(queryset):
    """
    Datums of the largest sizable measurement in `queryset`, or ``None``.

    The largest rather than the sum, because the workflows this feeds compute
    per measurement and combine the results; see :func:`grid_points`. NULL
    rows (unsizable measurements) do not participate.

    The database cannot validate a ``file_info`` document against its kind's
    schema the way the Python path does, so a corrupt document -- a resolution
    stored as something no integer cast accepts -- surfaces here as a
    ``DataError`` from the cast. That is a fault worth a log line, but sizing
    runs during task submission, and the one thing this guard must never do is
    fail *closed*: the savepoint keeps the surrounding transaction usable and
    the answer is "unknown".
    """
    expression = _points_expression()
    if expression is None:
        return None
    try:
        with transaction.atomic():
            return queryset.annotate(points=expression).aggregate(
                largest=Max("points")
            )["largest"]
    except DataError:
        _log.error(
            "Cannot size a set of measurements: a stored file_info document "
            "holds a resolution the integer cast rejects.",
            exc_info=True,
        )
        return None


def observed_bytes_per_point(use_cache=True):
    """
    Learned memory coefficient per workflow, in bytes per grid point.

    Derived only from analyses of a single measurement, because that is the one
    case where the number of grid points involved is unambiguous, and only from
    runs inside the configured window, so that the coefficient can fall again
    when a workflow is optimised. Runs on subjects below the minimum point
    count are excluded and the assumed process baseline is subtracted first;
    see the module docstring for why raw ``task_memory / points`` on a small
    subject is baseline, not coefficient. A workflow with no qualifying recent
    runs is absent from the result, and callers must treat that as "no
    estimate".

    ``task_end_time`` dates a run rather than ``task_start_time``, because that
    is when its memory was measured. It is set on both the success and the
    failure path, so completed runs always carry one.
    """
    if use_cache:
        cached = cache.get(CACHE_KEY)
        if cached is not None:
            return cached

    from .models import WorkflowResult

    expression = _points_expression("subject_measurement__")
    if expression is None:
        return {}

    window_days = _setting("TOPOBANK_ANALYSIS_MEMORY_WINDOW_DAYS", DEFAULT_WINDOW_DAYS)
    baseline = _setting("TOPOBANK_ANALYSIS_MEMORY_BASELINE", DEFAULT_BASELINE)
    min_points = _setting("TOPOBANK_ANALYSIS_MEMORY_MIN_POINTS", DEFAULT_MIN_POINTS)
    rows = (
        WorkflowResult.objects.filter(
            task_memory__isnull=False,
            task_memory__gt=0,
            task_end_time__gte=timezone.now() - timedelta(days=window_days),
            subject_measurement__isnull=False,
        )
        .annotate(points=expression)
        # Also excludes unsizable measurements: their `points` is NULL, and
        # NULL compares as unknown.
        .filter(points__gte=min_points)
        .values_list("workflow_name", "task_memory", "points")
    )

    ratios = defaultdict(list)
    try:
        with transaction.atomic():
            for workflow_name, task_memory, points in rows.iterator():
                # A peak below the assumed baseline carries no per-point
                # information; clamping it to zero instead would drag the
                # percentile down with fabricated "free" runs, so it is
                # skipped entirely.
                if points and task_memory > baseline:
                    ratios[workflow_name].append((task_memory - baseline) / points)
    except DataError:
        # A corrupt document makes the cast fail for the whole query, taking
        # every workflow's coefficient with it. Deliberately not cached: the
        # empty result is a degraded answer, not a learned one, and caching it
        # would keep the guard blind for an hour after the document is fixed.
        _log.error(
            "Cannot learn memory coefficients: a stored file_info document "
            "holds a resolution the integer cast rejects.",
            exc_info=True,
        )
        return {}

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
        measurement = analysis.subject_measurement
        # The registry is consulted directly rather than through
        # `measurement.adapter`: with no recorded kind, that property derives
        # one from the data file, and opening a file during task submission is
        # exactly what this module must never do. No kind, or a kind whose
        # plugin is not installed, means the size is unknown.
        if measurement.kind is None or not has_adapter(measurement.kind):
            return None
        try:
            return get_adapter(measurement.kind).nb_data_points(measurement)
        except pydantic.ValidationError:
            # A stored document that does not parse is a fault, but not one
            # this guard is allowed to turn into a refused analysis.
            _log.error(
                "Cannot size measurement %s: its file_info does not validate "
                "against the schema of kind '%s'.",
                measurement.id,
                measurement.kind,
                exc_info=True,
            )
            return None

    if analysis.subject_surface_id is not None:
        queryset = Measurement.objects.filter(surface_id=analysis.subject_surface_id)
    elif analysis.subject_tag_id is not None:
        return None
    else:
        surface_ids = list(analysis.surfaces.values_list("id", flat=True))
        if not surface_ids:
            return None
        queryset = Measurement.objects.filter(surface_id__in=surface_ids)

    return points_in_sql(queryset)


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
    baseline = _setting("TOPOBANK_ANALYSIS_MEMORY_BASELINE", DEFAULT_BASELINE)
    # The baseline was subtracted when the coefficient was learned, so it has
    # to be added back here: the budget is compared against the process's real
    # peak RSS, which includes it. It is deliberately outside the safety
    # factor - the spread the factor absorbs is in the per-point cost, not in
    # the interpreter footprint.
    return int(baseline + points * coefficient * safety_factor)


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
