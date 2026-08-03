"""
Tests for the metadata that accompanies a split-off data series.

Series data lives in its own file in the object store, so anything a plot needs
before fetching them has to be recorded next to the reference. That includes the
extent of the data, which is what lets a plot combining several results choose a
display unit that suits them (ContactEngineering/ce-ui#39).
"""

import numpy as np

from topobank.analysis.legacy.workflows import wrap_series


def _supplementary(series):
    """The metadata of each wrapped series, in order."""
    return [wrapped.supplementary for wrapped in wrap_series(series)]


def test_records_the_range_of_both_axes():
    (metadata,) = _supplementary(
        [{"name": "Height distribution", "x": [-2.0, 0.5, 3.0], "y": [0.1, 0.9, 0.2]}]
    )
    assert metadata["xRange"] == [-2.0, 3.0]
    assert metadata["yRange"] == [0.1, 0.9]


def test_keeps_the_existing_metadata():
    (metadata,) = _supplementary(
        [{"name": "Height distribution", "x": [1.0], "y": [2.0], "visible": False}]
    )
    assert metadata["name"] == "Height distribution"
    assert metadata["nbDataPoints"] == 1
    assert metadata["visible"] is False


def test_ignores_undefined_data_points():
    """A series can carry NaN for a point that has no value; it says nothing about
    the extent of the data."""
    (metadata,) = _supplementary(
        [{"name": "s", "x": [1.0, np.nan, 3.0], "y": [np.nan, 2.0, 4.0]}]
    )
    assert metadata["xRange"] == [1.0, 3.0]
    assert metadata["yRange"] == [2.0, 4.0]


def test_ignores_infinities():
    """A distribution can diverge, which is not an extent either."""
    (metadata,) = _supplementary(
        [{"name": "s", "x": [1.0, 2.0], "y": [np.inf, 5.0]}]
    )
    assert metadata["yRange"] == [5.0, 5.0]


def test_no_range_when_nothing_is_finite():
    (metadata,) = _supplementary([{"name": "s", "x": [np.nan], "y": [np.inf]}])
    assert "xRange" not in metadata
    assert "yRange" not in metadata


def test_no_range_for_an_empty_series():
    (metadata,) = _supplementary([{"name": "s", "x": [], "y": []}])
    assert metadata["nbDataPoints"] == 0
    assert "xRange" not in metadata
    assert "yRange" not in metadata


def test_series_without_a_y_axis():
    (metadata,) = _supplementary([{"name": "s", "x": [1.0, 4.0]}])
    assert metadata["xRange"] == [1.0, 4.0]
    assert "yRange" not in metadata


def test_ranges_are_plain_floats():
    """The metadata is serialized to JSON, so numpy scalars would have to be
    encoded specially."""
    (metadata,) = _supplementary(
        [{"name": "s", "x": np.array([1.0, 2.0]), "y": np.array([3.0, 4.0])}]
    )
    assert all(type(v) is float for v in metadata["xRange"] + metadata["yRange"])


def test_each_series_gets_its_own_range():
    first, second = _supplementary(
        [
            {"name": "a", "x": [1.0, 2.0], "y": [1.0, 1.0]},
            {"name": "b", "x": [10.0, 20.0], "y": [2.0, 2.0]},
        ]
    )
    assert first["xRange"] == [1.0, 2.0]
    assert second["xRange"] == [10.0, 20.0]
