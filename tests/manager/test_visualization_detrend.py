"""
Tests for the detrending that thumbnails and deep zoom images apply on top of a
measurement's own `detrend_mode` (`TOPOBANK_VISUALIZATION_DETREND_MODE`).
"""

import numpy as np
import pytest
from SurfaceTopography import Topography as STTopography
from SurfaceTopography import UniformLineScan

from topobank.manager.models import Topography
from topobank.testing.factories import Topography2DFactory

SIZE_X, SIZE_Y = 20.0, 40.0


def _tilted_topography():
    """A plane tilted in x and y, centered like a `detrend_mode="center"` read."""
    x = np.arange(32) * SIZE_X / 32
    y = np.arange(64) * SIZE_Y / 64
    X, Y = np.meshgrid(x, y, indexing="ij")
    return STTopography(
        0.5 + 3 * X + 7 * Y, physical_sizes=(SIZE_X, SIZE_Y), unit="µm"
    ).detrend("center")


def test_unset_shows_the_measurement_as_read(settings):
    settings.TOPOBANK_VISUALIZATION_DETREND_MODE = None
    st_topo = _tilted_topography()
    assert Topography(detrend_mode="center")._visualization_topography(st_topo) is st_topo


def test_tilt_is_removed_from_a_centered_measurement(settings):
    settings.TOPOBANK_VISUALIZATION_DETREND_MODE = "height"
    st_topo = _tilted_topography()
    visualized = Topography(detrend_mode="center")._visualization_topography(st_topo)
    assert visualized.detrend_mode == "height"
    # A pure plane leaves nothing to show once its tilt is gone
    np.testing.assert_allclose(visualized.heights(), 0, atol=1e-10)
    # The topography that was passed in keeps its tilt
    assert np.ptp(st_topo.heights()) > 1


def test_tilt_is_removed_from_a_line_scan(settings):
    settings.TOPOBANK_VISUALIZATION_DETREND_MODE = "height"
    x = np.arange(64) * SIZE_X / 64
    st_topo = UniformLineScan(2 * x, physical_sizes=SIZE_X, unit="µm").detrend("center")
    visualized = Topography(detrend_mode="center")._visualization_topography(st_topo)
    np.testing.assert_allclose(visualized.heights(), 0, atol=1e-10)


@pytest.mark.parametrize(
    "detrend_mode,visualization_mode",
    [("height", "height"), ("curvature", "height"), ("curvature", "curvature")],
)
def test_a_measurement_detrended_at_least_as_far_is_shown_as_is(
    settings, detrend_mode, visualization_mode
):
    settings.TOPOBANK_VISUALIZATION_DETREND_MODE = visualization_mode
    st_topo = _tilted_topography().detrend(detrend_mode)
    topo = Topography(detrend_mode=detrend_mode)
    assert topo._visualization_topography(st_topo) is st_topo


def test_curvature_mode_goes_further_than_a_measurement_that_only_removes_tilt(
    settings,
):
    settings.TOPOBANK_VISUALIZATION_DETREND_MODE = "curvature"
    st_topo = _tilted_topography().detrend("height")
    visualized = Topography(detrend_mode="height")._visualization_topography(st_topo)
    assert visualized.detrend_mode == "curvature"


def test_unknown_mode_is_rejected(settings):
    settings.TOPOBANK_VISUALIZATION_DETREND_MODE = "tilt"
    with pytest.raises(ValueError, match="TOPOBANK_VISUALIZATION_DETREND_MODE"):
        Topography(detrend_mode="center")._visualization_topography(
            _tilted_topography()
        )


@pytest.mark.django_db
def test_refresh_cache_renders_images_but_not_data_detrended(settings, mocker):
    settings.TOPOBANK_VISUALIZATION_DETREND_MODE = "height"
    render_thumbnail = mocker.spy(Topography, "_render_thumbnail")
    render_deepzoom = mocker.patch("topobank.manager.models.render_deepzoom")

    topo = Topography2DFactory(size_x=1, size_y=1, detrend_mode="center")

    assert render_thumbnail.call_args.kwargs["st_topo"].detrend_mode == "height"
    assert render_deepzoom.call_args.args[0].detrend_mode == "height"
    # Analyses read the measurement with its own detrending
    assert topo.read(allow_squeezed=False).detrend_mode == "center"
