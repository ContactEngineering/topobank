"""
Tests for the memory-guard sizing of analyses.

How many datums a measurement holds is a property of its kind, so the equations
live on the measurement adapters -- in two forms, a Python method for a single
instance and an ORM expression for the SQL aggregates. The central property is
that the two forms of one equation can never drift apart, and that a kind which
cannot be sized abstains instead of being sized wrongly: the guard's contract is
to fail open, and the one thing worse than no prediction is a confident wrong
one (see issue #1393).
"""

import pytest
from django.core.cache import cache

from topobank.analysis import sizing
from topobank.analysis.exceptions import AnalysisTooLargeError
from topobank.analysis.sizing import (
    check_memory_budget,
    estimate_memory,
    grid_points,
    observed_bytes_per_point,
    points_in_sql,
)
from topobank.manager.models import Measurement
from topobank.measurements.adapters import MeasurementAdapter
from topobank.measurements.registry import (
    get_adapter,
    get_adapters,
    register_adapter,
    unregister_adapter,
)
from topobank.testing.factories import (
    AnalysisFactoryWithoutResult,
    SurfaceFactory,
    Topography1DFactory,
    Topography2DFactory,
)

#: The sizing equation of every built-in kind: the `file_info` cache it reads,
#: and the number of datums that has to come out -- through *both* paths.
#: `test_every_registered_kind_appears_here` keeps this table complete, so a new
#: kind fails here until its author has decided how it is sized (possibly: not).
CASES = {
    "topography-map": ({"resolution_x": 128, "resolution_y": 64}, 128 * 64),
    "uniform-line-scan": ({"resolution_x": 128}, 128),
    # Twice the samples: arbitrary positions have to be stored alongside the
    # heights.
    "nonuniform-line-scan": ({"resolution_x": 128}, 2 * 128),
}


WORKFLOW = "topobank.testing.test"

GIB = 1024**3


@pytest.fixture(autouse=True)
def _fresh_coefficients():
    """Learned coefficients are cached process-wide; isolate each test."""
    cache.delete(sizing.CACHE_KEY)
    yield
    cache.delete(sizing.CACHE_KEY)


@pytest.fixture(autouse=True)
def _learn_from_single_runs(settings):
    """One observation per scenario is enough for these tests."""
    settings.TOPOBANK_ANALYSIS_MEMORY_MIN_SAMPLES = 1


def sized(kind, file_info):
    """A measurement of `kind` whose inspection cache is set directly."""
    topo = Topography2DFactory()
    Measurement.objects.filter(pk=topo.pk).update(
        kind=kind, file_info={"kind": kind, **file_info}
    )
    return Measurement.objects.get(pk=topo.pk)


def _subject(resolution_x, resolution_y=None):
    """A map, or -- without a second resolution -- a uniform line scan."""
    if resolution_y is None:
        return sized("uniform-line-scan", {"resolution_x": resolution_x})
    return sized(
        "topography-map",
        {"resolution_x": resolution_x, "resolution_y": resolution_y},
    )


def _completed_run(task_memory, resolution_x, resolution_y=None):
    """A finished analysis whose subject has the given grid resolution."""
    return AnalysisFactoryWithoutResult(
        subject_measurement=_subject(resolution_x, resolution_y),
        workflow_name=WORKFLOW,
        task_memory=task_memory,
    )


def _pending_analysis(resolution_x, resolution_y=None):
    """An analysis about to run on a subject of the given grid resolution."""
    return AnalysisFactoryWithoutResult(
        subject_measurement=_subject(resolution_x, resolution_y),
        workflow_name=WORKFLOW,
    )


def both_paths(measurement):
    """The Python answer and the SQL answer for one measurement."""
    python_answer = get_adapter(measurement.kind).nb_data_points(measurement)
    sql_answer = points_in_sql(Measurement.objects.filter(pk=measurement.pk))
    return python_answer, sql_answer


#
# The central property: one equation, two implementations, no drift
#


def test_every_builtin_kind_appears_in_the_equation_table():
    """
    A kind nobody thought about must fail loudly, here.

    Whoever adds a kind decides how it is sized -- implementing neither hook is
    a legitimate decision (the guard then abstains), but it has to be a
    decision, recorded by adding a row to `CASES`. Only the kinds this
    repository ships are held to that: an installed plugin registers kinds it
    cannot add to this table, so the comparison must not see them.
    """
    builtin_kinds = {
        kind
        for kind, adapter in get_adapters().items()
        if type(adapter).__module__ == "topobank.measurements.adapters"
    }
    assert set(CASES) == builtin_kinds


@pytest.mark.django_db
@pytest.mark.parametrize("kind", sorted(CASES))
def test_both_sizing_paths_agree(kind):
    """
    The Python path and the SQL path are the same equation.

    A kind that implements one hook and not the other fails with `None != N`;
    one that implements them differently fails with the two numbers.
    """
    file_info, expected = CASES[kind]
    measurement = sized(kind, file_info)

    python_answer, sql_answer = both_paths(measurement)

    assert python_answer == sql_answer == expected


@pytest.mark.django_db
@pytest.mark.parametrize("kind", sorted(CASES))
def test_an_uninspected_measurement_is_unknown_on_both_paths(kind):
    """No resolution recorded yet: unknown (None), never 0 or a guess."""
    measurement = sized(kind, {})

    assert both_paths(measurement) == (None, None)


@pytest.mark.django_db
def test_a_half_inspected_map_is_unknown_not_a_line_scan():
    """
    `resolution_x` recorded, `resolution_y` not: the size is unknown.

    Treating such a map as `resolution_x` points -- which a Coalesce-to-1 used
    to do -- would let a huge map past the memory guard on the strength of a
    partial inspection.
    """
    measurement = sized("topography-map", {"resolution_x": 40000})

    assert both_paths(measurement) == (None, None)


@pytest.mark.django_db
def test_a_huge_map_does_not_overflow_in_the_database():
    """
    50000 x 50000 is 2.5e9 points, beyond a 32-bit product.

    PostgreSQL multiplies `integer * integer` as an integer, so without the
    `BigIntegerField` casts this exact case -- the size of map the guard exists
    to catch -- would error out or wrap.
    """
    measurement = sized(
        "topography-map", {"resolution_x": 50000, "resolution_y": 50000}
    )

    assert both_paths(measurement) == (2_500_000_000, 2_500_000_000)


#
# Dispatch: every measurement is sized by its own kind's equation
#


@pytest.mark.django_db
def test_a_mixed_dataset_sizes_each_measurement_with_its_own_equation():
    """
    The aggregate is a CASE over `kind`, not one equation for all rows.

    The nonuniform scan here (2 x 300 = 600 datums) outweighs the map (100).
    A single shared resolution product would score the scan at 300 and get
    the dataset maximum wrong.
    """
    surface = SurfaceFactory()
    Topography2DFactory(surface=surface)  # inspected 10x10 map: 100 datums
    scan = Topography1DFactory(surface=surface)
    Measurement.objects.filter(pk=scan.pk).update(
        kind="nonuniform-line-scan",
        file_info={"kind": "nonuniform-line-scan", "resolution_x": 300},
    )
    analysis = AnalysisFactoryWithoutResult(subject_surface=surface)

    assert grid_points(analysis) == 600


@pytest.mark.django_db
def test_an_unsizable_measurement_does_not_shrink_the_dataset_maximum():
    """A NULL row must be skipped by the aggregate, not counted as 0."""
    surface = SurfaceFactory()
    Topography2DFactory(surface=surface)  # 100 datums
    stranger = Topography2DFactory(surface=surface)
    Measurement.objects.filter(pk=stranger.pk).update(
        kind="kind-of-an-uninstalled-plugin", file_info={}
    )
    analysis = AnalysisFactoryWithoutResult(subject_surface=surface)

    assert grid_points(analysis) == 100


#
# Failing open
#


@pytest.mark.django_db
def test_a_kind_without_an_adapter_abstains():
    """
    An uninstalled plugin's measurements stay analyzable.

    Sizing runs during task submission; raising here would turn a missing
    plugin into an outage for its data.
    """
    measurement = sized("kind-of-an-uninstalled-plugin", {})
    analysis = AnalysisFactoryWithoutResult(subject_measurement=measurement)

    assert grid_points(analysis) is None


@pytest.mark.django_db
def test_a_registered_kind_that_declines_to_size_abstains():
    """The base-class default, seen through the dispatcher on both paths."""

    @register_adapter
    class _SpectrumAdapter(MeasurementAdapter):
        class Meta:
            name = "test-unsized-spectrum"
            display_name = "Spectrum of unknowable size"

        @classmethod
        def claims_channel(cls, channel):
            return False

        def read(self, measurement, **kwargs):
            raise NotImplementedError

    try:
        measurement = sized("test-unsized-spectrum", {})
        analysis = AnalysisFactoryWithoutResult(subject_measurement=measurement)

        assert grid_points(analysis) is None
        assert points_in_sql(Measurement.objects.filter(pk=measurement.pk)) is None
    finally:
        unregister_adapter("test-unsized-spectrum")


@pytest.mark.django_db
def test_a_tag_subject_abstains():
    """Unchanged behaviour: a guard that abstains beats a guard that is wrong."""

    class _TagAnalysis:
        subject_measurement_id = None
        subject_surface_id = None
        subject_tag_id = 17

    assert grid_points(_TagAnalysis()) is None


@pytest.mark.django_db
def test_a_file_info_document_that_does_not_parse_abstains(caplog):
    """A corrupt cache is a fault worth a log line, not a refused analysis."""
    measurement = sized(
        "uniform-line-scan", {"resolution_x": 128, "resolution_y": 64}
    )  # resolution_y does not exist for this kind: the document cannot parse
    analysis = AnalysisFactoryWithoutResult(subject_measurement=measurement)

    assert grid_points(analysis) is None
    assert "Cannot size measurement" in caplog.text


@pytest.mark.django_db
def test_a_nonnumeric_resolution_does_not_abort_the_aggregate(caplog):
    """
    The SQL path cannot validate a document; a corrupt value reaches the cast.

    The database then raises rather than returning NULL, and without handling
    that would abort task submission -- the guard failing *closed* on a fault
    in somebody else's data. The whole set degrades to "unknown" instead, and
    the connection stays usable afterwards.
    """
    surface = SurfaceFactory()
    honest = Topography2DFactory(surface=surface)
    rotten = Topography2DFactory(surface=surface)
    Measurement.objects.filter(pk=rotten.pk).update(
        kind="uniform-line-scan",
        file_info={"kind": "uniform-line-scan", "resolution_x": "garbage"},
    )
    analysis = AnalysisFactoryWithoutResult(subject_surface=surface)

    assert grid_points(analysis) is None
    assert "the integer cast rejects" in caplog.text
    # The savepoint must leave the transaction usable.
    assert Measurement.objects.filter(pk=honest.pk).exists()


@pytest.mark.django_db
def test_a_nonnumeric_resolution_does_not_abort_the_learner(caplog):
    _completed_run(
        task_memory=sizing.DEFAULT_BASELINE + 200 * 8192 * 8192,
        resolution_x=8192,
        resolution_y=8192,
    )
    rotten = sized(
        "uniform-line-scan", {"resolution_x": "garbage"}
    )
    AnalysisFactoryWithoutResult(
        subject_measurement=rotten, workflow_name=WORKFLOW, task_memory=GIB
    )

    # One corrupt document takes the whole query down, so every coefficient is
    # lost until it is fixed -- degraded, logged, and deliberately not cached.
    assert observed_bytes_per_point(use_cache=False) == {}
    assert "Cannot learn memory coefficients" in caplog.text


#
# The learner uses the same equations
#


@pytest.mark.django_db
def test_the_coefficient_is_learned_with_the_equation_it_predicts_with(settings):
    """
    Learn from a run, predict for the same measurement: the two must meet.

    The trap this guards against is learning `(task_memory - baseline) /
    points` with one equation and predicting `points * coefficient` with
    another -- for a nonuniform scan that silently doubles or halves every
    prediction of the workflow. With the safety factor at 1, learning and
    predicting are exact inverses, so the prediction must reproduce the
    recorded peak to the byte.
    """
    settings.TOPOBANK_ANALYSIS_MEMORY_SAFETY_FACTOR = 1.0

    # A nonuniform scan of 10M samples is 20M datums (positions and heights)
    # -- above the minimum-points floor only if the learner counts them the
    # way the predictor does.
    datums = 2 * 10_000_000
    peak = sizing.DEFAULT_BASELINE + 1000 * datums
    analysis = AnalysisFactoryWithoutResult(
        subject_measurement=sized(
            "nonuniform-line-scan", {"resolution_x": 10_000_000}
        ),
        workflow_name=WORKFLOW,
        task_memory=peak,
    )

    coefficients = observed_bytes_per_point(use_cache=False)
    assert coefficients[WORKFLOW] == pytest.approx(1000.0)
    assert estimate_memory(analysis) == peak


#
# The process baseline stays out of the coefficient (issue #1393; ported from
# `main`, af418da). `task_memory` is peak RSS, several hundred MB of which is
# interpreter and libraries -- dividing it raw by a small subject's points
# yields megabytes per point, the high percentile latches onto those samples,
# and every following analysis of the workflow is refused with a TB-scale
# prediction.
#


@pytest.mark.django_db
def test_small_subjects_do_not_teach():
    # A line scan of 200 points that peaked at 1 GB: under the pre-#1393
    # arithmetic this is ~5 MB/point. It must not produce a coefficient.
    _completed_run(task_memory=GIB, resolution_x=200)

    assert WORKFLOW not in observed_bytes_per_point(use_cache=False)


@pytest.mark.django_db
def test_baseline_is_subtracted_when_learning_and_restored_when_predicting():
    points = 8192 * 8192  # above the minimum-points floor
    true_coefficient = 200  # B/point
    _completed_run(
        task_memory=sizing.DEFAULT_BASELINE + true_coefficient * points,
        resolution_x=8192,
        resolution_y=8192,
    )

    coefficients = observed_bytes_per_point(use_cache=False)
    assert coefficients[WORKFLOW] == pytest.approx(true_coefficient)

    analysis = _pending_analysis(resolution_x=8192, resolution_y=8192)
    expected = int(
        sizing.DEFAULT_BASELINE
        + points * true_coefficient * sizing.DEFAULT_SAFETY_FACTOR
    )
    assert estimate_memory(analysis) == expected


@pytest.mark.django_db
def test_poisoned_small_run_does_not_reject_ordinary_analyses(settings):
    """The #1393 scenario end to end."""
    settings.TOPOBANK_ANALYSIS_MEMORY_BUDGET = 64 * GIB

    # The poison: a tiny line scan whose peak RSS is all baseline.
    _completed_run(task_memory=GIB, resolution_x=200)
    # An honest observation on a large map: 200 B/point.
    big_points = 8192 * 8192
    _completed_run(
        task_memory=sizing.DEFAULT_BASELINE + 200 * big_points,
        resolution_x=8192,
        resolution_y=8192,
    )

    # An ordinary 1024 x 1024 measurement fits easily and must be allowed to
    # run. With the poisoned coefficient (~5 MB/point) it would have been
    # predicted at ~5 TB and refused.
    analysis = _pending_analysis(resolution_x=1024, resolution_y=1024)
    estimate = check_memory_budget(analysis)
    assert estimate is not None
    assert estimate < settings.TOPOBANK_ANALYSIS_MEMORY_BUDGET


@pytest.mark.django_db
def test_genuinely_too_large_analysis_is_still_refused(settings):
    settings.TOPOBANK_ANALYSIS_MEMORY_BUDGET = 64 * GIB

    big_points = 8192 * 8192
    _completed_run(
        task_memory=sizing.DEFAULT_BASELINE + 200 * big_points,
        resolution_x=8192,
        resolution_y=8192,
    )

    # 46000 x 46000 at 200 B/point x 1.2 safety is ~475 GB.
    analysis = _pending_analysis(resolution_x=46000, resolution_y=46000)
    with pytest.raises(AnalysisTooLargeError):
        check_memory_budget(analysis)


@pytest.mark.django_db
def test_runs_that_never_exceed_the_baseline_are_skipped():
    # Large subject, but the recorded peak is below the assumed baseline
    # (e.g. recorded by a fallback mechanism, or the workflow streamed its
    # data). There is no per-point information in it.
    _completed_run(task_memory=100 * 1024**2, resolution_x=8192, resolution_y=8192)

    assert WORKFLOW not in observed_bytes_per_point(use_cache=False)


@pytest.mark.django_db
def test_fails_open_without_history(settings):
    settings.TOPOBANK_ANALYSIS_MEMORY_BUDGET = 64 * GIB

    analysis = _pending_analysis(resolution_x=46000, resolution_y=46000)
    assert check_memory_budget(analysis) is None
