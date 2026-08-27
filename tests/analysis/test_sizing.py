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
from topobank.analysis.sizing import (
    estimate_memory,
    grid_points,
    observed_bytes_per_point,
    points_in_sql,
)
from topobank.manager.models import Measurement
from topobank.measurements.adapters import MeasurementAdapter
from topobank.measurements.registry import (
    get_adapter,
    get_kinds,
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


def sized(kind, file_info):
    """A measurement of `kind` whose inspection cache is set directly."""
    topo = Topography2DFactory()
    Measurement.objects.filter(pk=topo.pk).update(
        kind=kind, file_info={"kind": kind, **file_info}
    )
    return Measurement.objects.get(pk=topo.pk)


def both_paths(measurement):
    """The Python answer and the SQL answer for one measurement."""
    python_answer = get_adapter(measurement.kind).nb_data_points(measurement)
    sql_answer = points_in_sql(Measurement.objects.filter(pk=measurement.pk))
    return python_answer, sql_answer


#
# The central property: one equation, two implementations, no drift
#


def test_every_registered_kind_appears_in_the_equation_table():
    """
    A kind nobody thought about must fail loudly, here.

    Whoever adds a kind decides how it is sized -- implementing neither hook is
    a legitimate decision (the guard then abstains), but it has to be a
    decision, recorded by adding a row to `CASES`.
    """
    assert set(CASES) == set(get_kinds())


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


#
# The learner uses the same equations
#


@pytest.mark.django_db
def test_the_coefficient_is_learned_with_the_equation_it_predicts_with(settings):
    """
    Learn from a run, predict for the same measurement: the two must meet.

    The trap this guards against is learning `task_memory / points` with one
    equation and predicting `points * coefficient` with another -- for a
    nonuniform scan that silently doubles or halves every prediction of the
    workflow, which is the shape of the mispredictions in #1393.
    """
    settings.TOPOBANK_ANALYSIS_MEMORY_MIN_SAMPLES = 1
    settings.TOPOBANK_ANALYSIS_MEMORY_SAFETY_FACTOR = 1.0
    cache.delete(sizing.CACHE_KEY)

    measurement = sized("nonuniform-line-scan", {"resolution_x": 100})  # 200 datums
    analysis = AnalysisFactoryWithoutResult(
        subject_measurement=measurement,
        workflow_name="topobank.testing.sized",
        task_memory=200_000,
    )

    coefficients = observed_bytes_per_point(use_cache=False)
    assert coefficients["topobank.testing.sized"] == pytest.approx(1000.0)

    cache.delete(sizing.CACHE_KEY)
    assert estimate_memory(analysis) == pytest.approx(200_000)
