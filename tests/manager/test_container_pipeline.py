"""
Functional tests that import a real published surface container from
contact.engineering and exercise the topography data pipeline end to end:
file reading, the Celery task runner, metadata caching, and deepzoom /
squeezed-data generation.

The container is the published dataset https://doi.org/10.57703/ce-867nv
("Self-affine synthetic surface", three 500x500 synthetic surfaces). These
tests require network access and Celery eager mode (already enabled in the test
settings); they are skipped if the dataset cannot be reached.

The fixture downloads the container per test, so we keep the number of tests
small and assert several related things per test.
"""

import urllib.error

import pytest

from topobank.manager.models import Topography
from topobank.manager.tasks import import_container_from_url
from topobank.testing.factories import UserFactory

CONTAINER_URL = "https://contact.engineering/go/867nv"


@pytest.fixture
def imported_surface(db):
    """Import the published container, skipping the test if it is unreachable."""
    user = UserFactory()
    try:
        return import_container_from_url(user, CONTAINER_URL)
    except (urllib.error.URLError, OSError) as exc:  # pragma: no cover - network
        pytest.skip(f"Could not download container from {CONTAINER_URL}: {exc}")


@pytest.mark.django_db
def test_container_import_and_datafile_read(imported_surface):
    surface = imported_surface
    assert surface.name == "Self-affine synthetic surface"
    assert surface.topography_set.count() == 3

    # The raw data file of each measurement can be reconstructed into a real
    # SurfaceTopography object.
    for topo in surface.topography_set.all():
        st = topo.read()
        assert len(st.nb_grid_pts) == 2
        assert all(n > 0 for n in st.nb_grid_pts)
        assert all(s > 0 for s in st.physical_sizes)


@pytest.mark.django_db
def test_full_inspection_via_task_runner(imported_surface):
    from django.contrib.contenttypes.models import ContentType

    from topobank.taskapp.utils import task_dispatch

    topo = imported_surface.topography_set.order_by("name").first()

    # Reset cached state so the inspection recomputes everything from the raw
    # data file: metadata, bandwidth, thumbnail, deepzoom and squeezed data.
    topo.task_state = Topography.NOTRUN
    topo.data_source = None  # forces first-read metadata population
    topo.datafile_format = None
    topo.squeezed_datafile = None
    topo.save(
        update_fields=[
            "task_state",
            "data_source",
            "datafile_format",
            "squeezed_datafile",
        ]
    )

    # Drive the task runner synchronously. ``apply()`` runs the task in-process
    # with a real request context, going through TaskStateModel.run_task ->
    # Topography.task_worker -> refresh_cache (thumbnail / deepzoom / squeezed).
    ct = ContentType.objects.get_for_model(Topography)
    task_dispatch.apply(args=[ct.id, topo.id])

    topo.refresh_from_db()

    # The task runner drove the result to SUCCESS ...
    assert topo.task_state == Topography.SUCCESS
    # ... and refresh_cache repopulated the cached metadata ...
    assert topo.datafile_format is not None
    assert topo.channel_names
    assert topo.resolution_x is not None and topo.resolution_x > 0
    assert topo.size_x is not None and topo.size_x > 0
    assert topo.bandwidth_lower is not None
    # ... and regenerated the squeezed NetCDF representation.
    assert topo.squeezed_datafile is not None
    assert topo.squeezed_datafile.exists()

    # Human-readable undefined-data status is derivable.
    status = topo.get_undefined_data_status()
    assert isinstance(status, str) and status
