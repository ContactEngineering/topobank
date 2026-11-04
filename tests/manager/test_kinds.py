"""The measurement adapters (`topobank.manager.kinds`)."""

import types

import numpy as np
import pytest
from SurfaceTopography import NonuniformLineScan, Topography, UniformLineScan

from topobank.manager import kinds


def _channel(dim, unit="um", is_uniform=True):
    return types.SimpleNamespace(
        name="channel", dim=dim, unit=unit, is_uniform=is_uniform
    )


@pytest.mark.parametrize(
    "channel, kind",
    [
        (_channel(2), "topography-map"),
        (_channel(1), "uniform-line-scan"),
        (_channel(1, is_uniform=False), "nonuniform-line-scan"),
    ],
)
def test_each_height_channel_is_claimed_by_one_kind(channel, kind):
    assert kinds.infer_kind(channel) == kind
    claiming = [
        name
        for name, adapter in kinds.get_adapters().items()
        if adapter.claims_channel(channel)
    ]
    assert claiming == [kind]


def test_data_other_than_heights_is_claimed_by_no_kind():
    with pytest.raises(kinds.UnsupportedChannelError):
        kinds.infer_kind(_channel(2, unit=("um", "nN")))


def test_an_unknown_kind_is_reported_as_such():
    with pytest.raises(kinds.UnknownMeasurementKindError, match="not be installed"):
        kinds.get_adapter("xps-spectrum")


def test_a_kind_cannot_be_registered_twice():
    class Other(kinds.TopographyMapAdapter):
        class Meta:
            name = "topography-map"

    with pytest.raises(kinds.AlreadyRegisteredError):
        kinds.register_adapter(Other)


def test_a_plugin_can_register_a_kind_of_its_own():
    @kinds.register_adapter
    class Spectrum(kinds.MeasurementAdapter):
        class Meta:
            name = "test-spectrum"

        @classmethod
        def claims_channel(cls, channel):
            return channel.dim == 0

        def read(self, reader, params, apply_filters=True, with_instrument_info=True):
            return None

    try:
        assert kinds.infer_kind(_channel(0)) == "test-spectrum"
        adapter = kinds.get_adapter("test-spectrum")
        assert not adapter.has_deepzoom and not adapter.has_canonical_file
    finally:
        kinds.unregister_adapter("test-spectrum")


def test_only_a_map_has_deep_zoom_images():
    assert [
        name for name, adapter in kinds.get_adapters().items() if adapter.has_deepzoom
    ] == ["topography-map"]


def test_the_kind_of_data_read_without_one():
    assert kinds.adapter_of_data(Topography(np.zeros((4, 4)), (1, 1))).Meta.name == (
        "topography-map"
    )
    assert kinds.adapter_of_data(UniformLineScan(np.zeros(4), 1)).Meta.name == (
        "uniform-line-scan"
    )
    assert kinds.adapter_of_data(
        NonuniformLineScan(np.arange(4.0), np.zeros(4))
    ).Meta.name == ("nonuniform-line-scan")


def test_a_flat_map_has_a_thumbnail():
    """Normalizing the heights of a flat map would divide by zero."""
    image = kinds.get_adapter("topography-map").render_thumbnail(
        Topography(np.zeros((8, 8)), (1, 1)), format="png"
    )
    assert image.getvalue().startswith(b"\x89PNG")


def test_a_line_scan_thumbnail_is_a_plot():
    image = kinds.get_adapter("uniform-line-scan").render_thumbnail(
        UniformLineScan(np.sin(np.arange(16.0)), 1), format="png"
    )
    assert image.getvalue().startswith(b"\x89PNG")
