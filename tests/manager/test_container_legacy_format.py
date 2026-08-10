"""
Importing containers written before the metadata moved into JSON.

Every published dataset on contact.engineering is in the old layout, so import has
to keep reading it: height metadata as flat keys, the data channel as an index, and
the measurement list under ``topographies``.
"""

import io
import json
import zipfile

import pytest

from topobank.manager.container_schema import MeasurementMeta
from topobank.manager.import_zip import import_container_zip
from topobank.measurements.registry import MeasurementNotInspectedError
from topobank.testing.factories import UserFactory

LEGACY_ARCHIVE = {
    "versions": {"topobank": "1.57.3"},
    "created_at": "2024-01-01 00:00:00+00:00",
    "surfaces": [
        {
            "name": "Legacy dataset",
            "category": "exp",
            "description": "Written by an older TopoBank",
            "tags": ["legacy"],
            "is_published": False,
            "topographies": [
                {
                    "name": "example4.txt",
                    "datafile": {"original": "example4.txt"},
                    "size": [112.80791, 27.73965],
                    "unit": "µm",
                    "data_source": 0,
                    "detrend_mode": "height",
                    "fill_undefined_data_mode": "do-not-fill",
                    "is_periodic": False,
                    "measurement_date": "2018-01-02",
                    "description": "a legacy measurement",
                    "tags": ["tree"],
                    "instrument": {
                        "name": "Legacy profilometer",
                        "type": "contact-based",
                        "parameters": {"tip_radius": {"value": 10, "unit": "µm"}},
                    },
                }
            ],
        }
    ],
}


class TestSchemaReadsBothLayouts:
    """`MeasurementMeta` is the single place that understands both layouts."""

    def test_legacy_flat_keys_become_metadata(self):
        meta = MeasurementMeta(**LEGACY_ARCHIVE["surfaces"][0]["topographies"][0])
        kwargs = meta.to_measurement_kwargs()

        # The kind is deliberately left for the first inspection to determine from
        # the file: the selected channel is authoritative, not the metadata.
        assert kwargs["kind"] == ""
        metadata = kwargs["metadata"]
        assert metadata["size_x"] == 112.80791
        assert metadata["size_y"] == 27.73965
        assert metadata["unit"] == "µm"
        assert metadata["detrend_mode"] == "height"
        assert metadata["instrument"]["name"] == "Legacy profilometer"
        assert metadata["instrument"]["type"] == "contact-based"

    def test_legacy_channel_index_becomes_a_hint(self):
        entry = dict(LEGACY_ARCHIVE["surfaces"][0]["topographies"][0], data_source=2)
        kwargs = MeasurementMeta(**entry).to_measurement_kwargs()

        assert kwargs["channel_name"] is None
        # Carried over so that inspection selects the channel the archive refers
        # to rather than the reader's default.
        assert kwargs["channel_index_hint"] == 2

    def test_archive_without_a_channel_defaults_to_the_first(self):
        entry = {
            k: v
            for k, v in LEGACY_ARCHIVE["surfaces"][0]["topographies"][0].items()
            if k != "data_source"
        }
        kwargs = MeasurementMeta(**entry).to_measurement_kwargs()
        assert kwargs["channel_index_hint"] == 0

    def test_current_layout_is_used_as_is(self):
        meta = MeasurementMeta(
            name="m.txt",
            datafile={"original": "m.txt"},
            kind="uniform-line-scan",
            metadata={
                "kind": "uniform-line-scan",
                "size_x": 1.0,
                "unit": "nm",
            },
            channel={"name": "Height"},
        )
        kwargs = meta.to_measurement_kwargs()

        assert kwargs["kind"] == "uniform-line-scan"
        assert kwargs["metadata"]["size_x"] == 1.0
        assert kwargs["channel_name"] == "Height"
        assert kwargs["channel_occurrence"] is None
        assert kwargs["channel_index_hint"] is None

    def test_channel_occurrence_survives(self):
        meta = MeasurementMeta(
            name="m.txt",
            datafile={"original": "m.txt"},
            kind="uniform-line-scan",
            metadata={"kind": "uniform-line-scan"},
            channel={"name": "Height", "occurrence": 1},
        )
        assert meta.to_measurement_kwargs()["channel_occurrence"] == 1


def make_archive(metadata, datafile_name, datafile_bytes):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as zf:
        zf.writestr("index.json", json.dumps(metadata))
        zf.writestr(datafile_name, datafile_bytes)
    buffer.seek(0)
    return buffer


@pytest.mark.django_db
def test_import_of_a_legacy_archive():
    """End to end: a legacy archive imports and its measurement becomes readable."""
    from topobank.testing.data import FIXTURE_DATA_DIR

    with open(f"{FIXTURE_DATA_DIR}/example4.txt", mode="rb") as f:
        datafile_bytes = f.read()

    user = UserFactory()
    archive = make_archive(LEGACY_ARCHIVE, "example4.txt", datafile_bytes)
    with zipfile.ZipFile(archive, mode="r") as zf:
        zf.filename = "legacy.zip"
        (surface,) = import_container_zip(zf, user)

    assert surface.name == "Legacy dataset"
    (measurement,) = surface.measurements.all()

    # Imported metadata is in place before anything reads the file...
    assert measurement.metadata["size_x"] == 112.80791
    assert measurement.channel_index_hint == 0
    assert measurement.channel_name is None

    # ...but the kind follows from the selected data channel, which means the
    # record is not readable until it has been inspected - the same state a
    # freshly uploaded measurement is in. Importing does not read data files.
    assert measurement.kind == ""
    with pytest.raises(MeasurementNotInspectedError):
        measurement.read()

    # ...and the inspection determines the kind and resolves the channel name.
    measurement.refresh_cache()

    assert measurement.kind == "topography-map"
    assert measurement.channel_name is not None
    assert measurement.channel_index_hint is None
    assert measurement.meta.detrend_mode == "height"
    assert measurement.meta.instrument.name == "Legacy profilometer"
    assert measurement.read() is not None


@pytest.mark.django_db
def test_legacy_archive_does_not_reimport_instrument_metadata_from_the_file():
    """
    Metadata the archive carries wins over what the data file says.

    The file's optional metadata is only consulted on a measurement that has none,
    so an import cannot overwrite what the archive recorded.
    """
    from topobank.testing.data import FIXTURE_DATA_DIR

    with open(f"{FIXTURE_DATA_DIR}/example3.di", mode="rb") as f:
        datafile_bytes = f.read()

    archive_metadata = json.loads(json.dumps(LEGACY_ARCHIVE))
    entry = archive_metadata["surfaces"][0]["topographies"][0]
    entry["name"] = "example3.di"
    entry["datafile"]["original"] = "example3.di"
    entry["instrument"]["name"] = "From the archive"

    user = UserFactory()
    archive = make_archive(archive_metadata, "example3.di", datafile_bytes)
    with zipfile.ZipFile(archive, mode="r") as zf:
        zf.filename = "legacy.zip"
        (surface,) = import_container_zip(zf, user)

    (measurement,) = surface.measurements.all()
    assert not measurement.is_first_inspection  # the archive supplied metadata
    measurement.refresh_cache()

    assert measurement.meta.instrument.name == "From the archive"
