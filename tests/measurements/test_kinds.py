"""
Tests for the kind a measurement is recorded as, and what follows from it.

`Measurement.kind` is written while the data file is inspected and from then on
decides which measurement type handles the record: how it is read, whether it has
a Deep Zoom pyramid, whether its data can be interpreted at all.
"""

import pytest

from topobank.manager.models import Measurement
from topobank.measurements.registry import (
    MeasurementNotInspectedError,
    UnknownMeasurementKindError,
)
from topobank.testing.factories import Topography1DFactory, Topography2DFactory


@pytest.mark.django_db
def test_a_map_is_recorded_as_a_topography_map():
    measurement = Topography2DFactory()

    assert measurement.kind == "topography-map"
    assert measurement.measurement_type.has_deepzoom


@pytest.mark.django_db
def test_a_line_scan_is_recorded_as_a_line_scan():
    measurement = Topography1DFactory()

    assert measurement.kind in ("uniform-line-scan", "nonuniform-line-scan")
    # A line scan has no Deep Zoom pyramid; that is what the capability is for,
    # rather than testing `size_y` for null somewhere.
    assert not measurement.measurement_type.has_deepzoom


@pytest.mark.django_db
def test_the_kind_survives_a_reload():
    """It is a stored column, not something recomputed on access."""
    measurement = Topography2DFactory()

    assert Measurement.objects.get(pk=measurement.pk).kind == "topography-map"


@pytest.mark.django_db
def test_reinspection_does_not_reinterpret_an_existing_measurement(mocker):
    """
    A measurement keeps the kind it was created with.

    Refreshing the cache re-reads the file, and a reader that has meanwhile changed
    its mind about a channel must not silently turn stored data into a different
    kind of measurement. Asserted by watching `infer_kind`, because a rule that
    merely happened to infer the same value again would pass a check on the stored
    kind while still being wrong.
    """
    measurement = Topography2DFactory()
    assert measurement.kind == "topography-map"
    infer_kind = mocker.patch(
        "topobank.manager.models.infer_kind", return_value="something-else"
    )

    measurement.refresh_cache()

    infer_kind.assert_not_called()
    assert Measurement.objects.get(pk=measurement.pk).kind == "topography-map"


@pytest.mark.django_db
def test_a_first_inspection_records_what_was_inferred(mocker):
    """The counterpart: with no kind yet, inference decides and is stored."""
    measurement = Topography2DFactory()
    Measurement.objects.filter(pk=measurement.pk).update(kind=None)
    measurement.refresh_from_db()

    measurement.refresh_cache()

    assert Measurement.objects.get(pk=measurement.pk).kind == "topography-map"


@pytest.mark.django_db
def test_a_measurement_with_no_recorded_kind_is_still_readable():
    """
    Importing a container creates measurements that were never inspected.

    Their metadata comes from the archive, not from reading the file, so no kind
    was ever recorded -- but the data file is right there and the measurement has
    to stay readable. The kind is derived from the file on demand.
    """
    measurement = Topography2DFactory()
    Measurement.objects.filter(pk=measurement.pk).update(kind=None)
    measurement.refresh_from_db()

    assert measurement.measurement_type.Meta.name == "topography-map"
    assert measurement.read() is not None
    # Deriving it does not quietly record it; inspection is what stores a kind.
    assert Measurement.objects.get(pk=measurement.pk).kind is None


@pytest.mark.django_db
def test_a_measurement_with_neither_kind_nor_data_file_says_so():
    measurement = Topography2DFactory()
    measurement.kind = None
    measurement.datafile = None

    with pytest.raises(MeasurementNotInspectedError, match="derive one from"):
        measurement.measurement_type

    assert not measurement.has_known_kind


@pytest.mark.django_db
def test_the_cheap_interpretability_check_does_not_open_the_data_file(mocker):
    """
    `has_known_kind` is used to decide whether to offer data at all.

    It answers from the recorded kind alone, so that listing many measurements
    does not turn into one file open each.
    """
    measurement = Topography2DFactory()
    Measurement.objects.filter(pk=measurement.pk).update(kind=None)
    measurement.refresh_from_db()
    reader = mocker.patch("topobank.manager.models.get_topography_reader")

    assert not measurement.has_known_kind
    reader.assert_not_called()


@pytest.mark.django_db
def test_a_measurement_from_an_uninstalled_plugin_stays_usable_as_a_record():
    """
    Graceful degradation: the record survives its plugin.

    Only interpreting the data is blocked -- the measurement must still be
    listable, renameable and deletable, or an uninstalled plugin would strand
    whatever it created.
    """
    measurement = Topography2DFactory()
    Measurement.objects.filter(pk=measurement.pk).update(kind="gone-with-the-plugin")
    measurement = Measurement.objects.get(pk=measurement.pk)

    assert not measurement.has_known_kind
    with pytest.raises(UnknownMeasurementKindError, match="gone-with-the-plugin"):
        measurement.read()

    # ... but the record itself is untouched by that.
    measurement.name = "renamed.txt"
    measurement.save(update_fields=["name"])
    assert Measurement.objects.get(pk=measurement.pk).name == "renamed.txt"
    measurement.delete()
    assert not Measurement.objects.filter(pk=measurement.pk).exists()


@pytest.mark.django_db
def test_reading_goes_through_the_registered_type(mocker):
    """`Measurement.read` must dispatch rather than branch on field values."""
    measurement = Topography2DFactory()
    read = mocker.patch.object(
        type(measurement.measurement_type), "read", return_value="data"
    )

    result = measurement.read(allow_squeezed=False)

    assert result == "data"
    assert read.call_args.kwargs["allow_canonical"] is False


@pytest.mark.django_db
def test_a_measurement_imported_from_a_container_can_be_read():
    """
    The end-to-end version of the case above, through the real import path.

    Importing builds measurements straight from the archive's metadata without
    ever inspecting a file, so nothing records a kind. This goes through
    `import_container_zip` rather than nulling the column by hand, because the
    absence of a kind there is a property of the import path and would survive a
    fix that only made the hand-written case pass.
    """
    import os
    import tempfile
    import zipfile

    from topobank.manager.export_zip import export_container_zip
    from topobank.manager.import_zip import import_container_zip
    from topobank.testing.factories import SurfaceFactory, UserFactory

    user = UserFactory()
    surface = SurfaceFactory(created_by=user)
    Topography2DFactory(surface=surface)

    outfile = tempfile.NamedTemporaryFile(mode="wb", delete=False)
    export_container_zip(outfile, [surface])
    outfile.close()
    try:
        with zipfile.ZipFile(outfile.name, mode="r") as archive:
            (imported,) = import_container_zip(archive, UserFactory())
    finally:
        os.remove(outfile.name)

    (measurement,) = imported.measurements.all()
    assert measurement.kind is None  # never inspected
    data = measurement.read()
    assert len(data.nb_grid_pts) == 2
