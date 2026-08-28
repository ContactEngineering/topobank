"""
Tests for the memory-budget estimator (``topobank.analysis.sizing``).

The regression at the heart of these tests is issue #1393: coefficients were
learned as raw ``task_memory / points``, and peak RSS includes several hundred
MB of interpreter/Django baseline. A run on a small subject therefore taught
the estimator ``baseline / points`` - megabytes per point - and the high
percentile latched onto those samples, so every following analysis of that
workflow was refused with a TB-scale prediction regardless of its actual size.
"""

import pytest
from django.core.cache import cache

from topobank.analysis import sizing
from topobank.analysis.exceptions import AnalysisTooLargeError
from topobank.analysis.models import WorkflowResult
from topobank.manager.models import Topography
from topobank.testing.factories import TopographyAnalysisFactory

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


def _completed_run(task_memory, resolution_x, resolution_y=None):
    """A finished analysis whose subject has the given grid resolution."""
    analysis = TopographyAnalysisFactory()
    Topography.objects.filter(pk=analysis.subject_topography_id).update(
        resolution_x=resolution_x, resolution_y=resolution_y
    )
    WorkflowResult.objects.filter(pk=analysis.pk).update(task_memory=task_memory)
    analysis.refresh_from_db()
    return analysis


def _pending_analysis(resolution_x, resolution_y=None):
    """An analysis about to run on a subject of the given grid resolution."""
    analysis = TopographyAnalysisFactory()
    Topography.objects.filter(pk=analysis.subject_topography_id).update(
        resolution_x=resolution_x, resolution_y=resolution_y
    )
    WorkflowResult.objects.filter(pk=analysis.pk).update(task_memory=None)
    analysis.refresh_from_db()
    return analysis


@pytest.mark.django_db
def test_small_subjects_do_not_teach():
    # A line scan of 200 points that peaked at 1 GB: under the pre-#1393
    # arithmetic this is ~5 MB/point. It must not produce a coefficient.
    _completed_run(task_memory=GIB, resolution_x=200)

    assert WORKFLOW not in sizing.observed_bytes_per_point(use_cache=False)


@pytest.mark.django_db
def test_baseline_is_subtracted_when_learning_and_restored_when_predicting(settings):
    settings.TOPOBANK_ANALYSIS_MEMORY_BASELINE = sizing.DEFAULT_BASELINE
    points = 8192 * 8192  # above the minimum-points floor
    true_coefficient = 200  # B/point
    _completed_run(
        task_memory=sizing.DEFAULT_BASELINE + true_coefficient * points,
        resolution_x=8192,
        resolution_y=8192,
    )

    coefficients = sizing.observed_bytes_per_point(use_cache=False)
    assert coefficients[WORKFLOW] == pytest.approx(true_coefficient)

    analysis = _pending_analysis(resolution_x=8192, resolution_y=8192)
    expected = int(
        sizing.DEFAULT_BASELINE
        + points * true_coefficient * sizing.DEFAULT_SAFETY_FACTOR
    )
    assert sizing.estimate_memory(analysis) == expected


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
    estimate = sizing.check_memory_budget(analysis)
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
        sizing.check_memory_budget(analysis)


@pytest.mark.django_db
def test_runs_that_never_exceed_the_baseline_are_skipped():
    # Large subject, but the recorded peak is below the assumed baseline
    # (e.g. recorded by a fallback mechanism, or the workflow streamed its
    # data). There is no per-point information in it.
    _completed_run(task_memory=100 * 1024**2, resolution_x=8192, resolution_y=8192)

    assert WORKFLOW not in sizing.observed_bytes_per_point(use_cache=False)


@pytest.mark.django_db
def test_fails_open_without_history(settings):
    settings.TOPOBANK_ANALYSIS_MEMORY_BUDGET = 64 * GIB

    analysis = _pending_analysis(resolution_x=46000, resolution_y=46000)
    assert sizing.check_memory_budget(analysis) is None
