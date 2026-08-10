"""
Functional tests that import a real published surface container from
contact.engineering and exercise the measurement data pipeline end to end:
file reading, the Celery task runner, metadata caching, and deepzoom /
squeezed-data generation.

The container is in the format written before measurement kinds existed, so these
tests also cover the legacy import path that every published dataset needs.

The container is the published dataset https://doi.org/10.57703/ce-867nv
("Self-affine synthetic surface", three 500x500 synthetic surfaces). These
tests require network access and Celery eager mode (already enabled in the test
settings); they are skipped if the dataset cannot be reached.

The fixture downloads the container per test, so we keep the number of tests
small and assert several related things per test.
"""

import pytest

from topobank.manager.models import Measurement
from topobank.measurements.registry import MeasurementNotInspectedError
from topobank.testing.factories import UserFactory
from topobank.testing.utils import import_container_from_url_or_skip

CONTAINER_URL = "https://contact.engineering/go/867nv"


@pytest.fixture
def imported_surface(db):
    """Import the published container, skipping the test if it is unreachable."""
    return import_container_from_url_or_skip(UserFactory(), CONTAINER_URL)


@pytest.mark.django_db
def test_container_import_and_datafile_read(imported_surface):
    surface = imported_surface
    assert surface.name == "Self-affine synthetic surface"
    assert surface.measurements.count() == 3

    for measurement in surface.measurements.all():
        # This container predates measurement kinds, and the kind follows from the
        # selected data channel rather than from the archive's metadata, so it is
        # unknown until the file has been inspected. Until then the record exists
        # and carries the archive's metadata, but its data cannot be read - the
        # same state a freshly uploaded measurement is in.
        assert measurement.kind == ""
        assert measurement.metadata  # ...but the archive's metadata is there
        with pytest.raises(MeasurementNotInspectedError):
            measurement.read()

        measurement.refresh_cache()

        # Inspection determined the kind and resolved the channel by name.
        assert measurement.kind == "topography-map"
        assert measurement.channel_name

        # The raw data file can now be reconstructed into a real
        # SurfaceTopography object.
        st = measurement.read()
        assert len(st.nb_grid_pts) == 2
        assert all(n > 0 for n in st.nb_grid_pts)
        assert all(s > 0 for s in st.physical_sizes)


@pytest.mark.django_db
def test_full_inspection_via_task_runner(imported_surface):
    from django.contrib.contenttypes.models import ContentType

    from topobank.taskapp.utils import task_dispatch

    topo = imported_surface.measurements.order_by("name").first()

    # Reset cached state so the inspection recomputes everything from the raw
    # data file: metadata, bandwidth, thumbnail, deepzoom and squeezed data.
    topo.task_state = Measurement.NOTRUN
    topo.channel_name = None  # forces the channel to be resolved from the file
    topo.datafile_format = None
    topo.squeezed_datafile = None
    topo.save(
        update_fields=[
            "task_state",
            "channel_name",
            "datafile_format",
            "squeezed_datafile",
        ]
    )

    # Drive the task runner synchronously. ``apply()`` runs the task in-process
    # with a real request context, going through TaskStateModel.run_task ->
    # Measurement.task_worker -> refresh_cache (thumbnail / deepzoom / squeezed).
    ct = ContentType.objects.get_for_model(Measurement)
    task_dispatch.apply(args=[ct.id, topo.id])

    topo.refresh_from_db()

    # The task runner drove the result to SUCCESS ...
    assert topo.task_state == Measurement.SUCCESS
    # ... and refresh_cache determined the kind, resolved the channel and
    # repopulated the cached metadata ...
    assert topo.datafile_format is not None
    assert topo.kind == "topography-map"
    assert topo.channel_name
    file_info = topo.info
    assert file_info.channels
    assert file_info.resolution_x is not None and file_info.resolution_x > 0
    assert file_info.bandwidth_lower is not None
    assert topo.meta.size_x is not None and topo.meta.size_x > 0
    # ... and regenerated the squeezed NetCDF representation.
    assert topo.squeezed_datafile is not None
    assert topo.squeezed_datafile.exists()

    # Human-readable undefined-data status is derivable.
    status = topo.get_undefined_data_status()
    assert isinstance(status, str) and status
