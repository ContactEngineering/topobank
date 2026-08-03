"""
Tests for the trend that detrending subtracts from a measurement.

`Topography.detrend_parameters` records what was removed — the slope of the tilt,
the radius of the curvature — so the UI can show which correction is in effect
rather than only naming the mode.
"""

import numpy as np
import pytest
from SurfaceTopography import NonuniformLineScan, Topography, UniformLineScan

from topobank.manager.utils import detrend_parameters
from topobank.testing.factories import Topography2DFactory

# A tilt of 3 in x and 7 in y, and a cylindrical curvature of radius 50, on a
# scan whose two directions have different extents so that a slope normalized by
# the wrong one would show up.
SIZE_X, SIZE_Y = 20.0, 40.0
SLOPE_X, SLOPE_Y = 3.0, 7.0
RADIUS = 50.0


def _grid():
    x = np.arange(32) * SIZE_X / 32
    y = np.arange(64) * SIZE_Y / 64
    return np.meshgrid(x, y, indexing="ij")


def _tilted_topography():
    X, Y = _grid()
    return Topography(
        0.5 + SLOPE_X * X + SLOPE_Y * Y, physical_sizes=(SIZE_X, SIZE_Y), unit="µm"
    )


def _curved_topography():
    """Curved in x only, like a cylinder lying along y."""
    X, Y = _grid()
    return Topography(
        X**2 / (2 * RADIUS), physical_sizes=(SIZE_X, SIZE_Y), unit="µm"
    )


def test_slopes_are_dimensionless_ratios():
    parameters = detrend_parameters(_tilted_topography().detrend("height"))
    assert parameters["slope_x"] == pytest.approx(SLOPE_X)
    assert parameters["slope_y"] == pytest.approx(SLOPE_Y)


def test_tilt_removal_reports_no_radius():
    parameters = detrend_parameters(_tilted_topography().detrend("height"))
    assert "radius_x" not in parameters
    assert "radius_y" not in parameters


def test_curvature_removal_reports_the_radius():
    parameters = detrend_parameters(_curved_topography().detrend("curvature"))
    assert parameters["radius_x"] == pytest.approx(RADIUS, rel=1e-6)


def test_a_direction_the_fit_found_flat_has_no_radius():
    """The least-squares fit leaves quadratic coefficients at the level of
    numerical noise in a flat direction; inverting those would report a radius of
    order 1e17 µm."""
    parameters = detrend_parameters(_curved_topography().detrend("curvature"))
    assert "radius_y" not in parameters


def test_subtracting_the_mean_fits_no_trend():
    assert detrend_parameters(_tilted_topography().detrend("center")) == {}


def test_a_line_scan_has_no_y_component():
    x = np.arange(32) * SIZE_X / 32
    line_scan = UniformLineScan(
        0.5 + SLOPE_X * x, physical_sizes=SIZE_X, unit="µm"
    )
    parameters = detrend_parameters(line_scan.detrend("height"))
    assert parameters["slope_x"] == pytest.approx(SLOPE_X)
    assert "slope_y" not in parameters
    assert "radius_y" not in parameters


def test_a_nonuniform_line_scan_reports_its_slope():
    """A nonuniform fit is parameterized in real positions rather than in
    fractional ones, so it needs no normalization by the extent of the scan."""
    positions = np.array([0.0, 1.0, 3.0, 7.0, 11.0])
    line_scan = NonuniformLineScan(
        positions, 0.5 + SLOPE_X * positions, unit="µm"
    )
    parameters = detrend_parameters(line_scan.detrend("height"))
    assert parameters["slope_x"] == pytest.approx(SLOPE_X)


def test_a_nonuniform_line_scan_reports_its_radius():
    positions = np.linspace(0, 11, 40)
    line_scan = NonuniformLineScan(
        positions, positions**2 / (2 * RADIUS), unit="µm"
    )
    parameters = detrend_parameters(line_scan.detrend("curvature"))
    assert parameters["radius_x"] == pytest.approx(RADIUS, rel=1e-6)


def test_a_topography_that_was_not_detrended_fits_no_trend():
    assert detrend_parameters(_tilted_topography()) == {}


@pytest.mark.django_db
def test_inspection_stores_the_parameters():
    topo = Topography2DFactory(detrend_mode="height")
    assert set(topo.detrend_parameters) == {"slope_x", "slope_y"}
    assert all(isinstance(v, float) for v in topo.detrend_parameters.values())


@pytest.mark.django_db
def test_parameters_are_unknown_before_inspection():
    topo = Topography2DFactory(task_state="pe")
    topo.detrend_parameters = None
    topo.save()
    topo.refresh_from_db()
    assert topo.detrend_parameters is None
