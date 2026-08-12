"""
Tests for thumbnail rendering in the measurement adapters.

Rendering is the one adapter responsibility that runs numerical code on the data
rather than delegating, so its edge cases are worth pinning down here rather than
through the model.
"""

import numpy as np
import PIL.Image
import pytest

from topobank.measurements.adapters import (
    NonuniformLineScanAdapter,
    TopographyMapAdapter,
    UniformLineScanAdapter,
)


class FakeMap:
    """A two-dimensional data object with the attributes the adapter reads."""

    def __init__(self, heights):
        self._heights = heights
        self.physical_sizes = (1.0, 1.0)

    def heights(self):
        return self._heights


class FakeLineScan:
    def __init__(self, y):
        self._y = y

    def positions_and_heights(self):
        return np.arange(len(self._y), dtype=float), self._y


def open_image(image_file):
    image_file.seek(0)
    return PIL.Image.open(image_file)


def unique_colors(image):
    """Number of distinct RGB values in a rendered thumbnail."""
    pixels = np.asarray(image.convert("RGB")).reshape(-1, 3)
    return len(np.unique(pixels, axis=0))


def test_a_map_thumbnail_renders():
    data = FakeMap(np.linspace(0, 1, 64).reshape(8, 8))

    image = open_image(TopographyMapAdapter().render_thumbnail(None, data))

    assert image.size[0] > 0 and image.size[1] > 0


def test_a_flat_map_renders_a_uniform_thumbnail():
    """
    A perfectly flat map must not divide by zero.

    Normalizing heights by `max - min` is a zero division when every height is the
    same -- a zeroed or synthetic surface -- and the NaNs it produces go straight
    into the colormap, whose output for NaN is not something to rely on.
    """
    data = FakeMap(np.full((8, 8), 42.0))

    with np.errstate(invalid="raise", divide="raise"):
        image = open_image(TopographyMapAdapter().render_thumbnail(None, data))

    assert unique_colors(image) == 1, "a flat map should render as a single colour"


def test_a_flat_map_at_zero_also_renders():
    """The all-zeros case specifically: `max`, `min` and their difference agree."""
    data = FakeMap(np.zeros((8, 8)))

    with np.errstate(invalid="raise", divide="raise"):
        image = open_image(TopographyMapAdapter().render_thumbnail(None, data))

    assert unique_colors(image) == 1


@pytest.mark.parametrize(
    "adapter", [UniformLineScanAdapter(), NonuniformLineScanAdapter()]
)
def test_a_flat_line_scan_renders(adapter):
    """Line scans plot rather than normalize, but pin the same edge case down."""
    image = open_image(adapter.render_thumbnail(None, FakeLineScan(np.zeros(16))))

    assert image.size[0] > 0
