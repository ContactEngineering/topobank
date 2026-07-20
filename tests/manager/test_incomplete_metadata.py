"""
Tests for the `TOPOBANK_REJECT_INCOMPLETE_METADATA` global flag.

A file can be of a supported format and read successfully, yet not contain the
metadata (physical size, unit) required to process it. By default such a file is
accepted and the user is expected to fill in the missing metadata through the UI.
When `TOPOBANK_REJECT_INCOMPLETE_METADATA` is enabled, the file is rejected with an
explicit error that distinguishes it from an unsupported file format.
"""

import types

import pytest
from django.test import override_settings

from topobank.manager.models import Topography
from topobank.taskapp.models import IncompleteMetadataError, TaskStateModel
from topobank.testing.factories import ManifestFactory, SurfaceFactory

# 10x10.txt is a bare matrix of numbers: readable (format 'asc'), but with no
# physical size, no unit and no height scale. example4.txt is of the same format
# but carries size, unit and height scale. dummy.txt is not a valid file of any
# supported format.
INCOMPLETE_DATAFILE = "10x10.txt"
COMPLETE_DATAFILE = "example4.txt"
UNSUPPORTED_DATAFILE = "dummy.txt"


def _make_topography(surface, filename):
    """Create a fresh, uninspected Topography backed by the given fixture file."""
    datafile = ManifestFactory(filename=filename, permissions=surface.permissions)
    topo = Topography(
        surface=surface,
        created_by=surface.created_by,
        permissions=surface.permissions,
        name=filename,
        datafile=datafile,
        data_source=None,
    )
    # Creating a new object does not dispatch an inspection task, so the file is
    # not read until we call refresh_cache()/run_task() explicitly below.
    topo.save()
    return topo


def _fake_celery_task():
    # task_id is a UUIDField, so the request id must be a valid UUID.
    return types.SimpleNamespace(
        request=types.SimpleNamespace(id="00000000-0000-0000-0000-000000000001")
    )


@pytest.mark.django_db
@override_settings(TOPOBANK_REJECT_INCOMPLETE_METADATA=False)
def test_incomplete_metadata_accepted_by_default():
    """With the flag off, a readable file with missing metadata is accepted."""
    surface = SurfaceFactory()
    topo = _make_topography(surface, INCOMPLETE_DATAFILE)

    topo.refresh_cache()

    assert not topo.is_metadata_complete
    assert topo.size_editable
    assert topo.unit_editable
    assert topo.size_x is None
    assert topo.unit is None


@pytest.mark.django_db
@override_settings(TOPOBANK_REJECT_INCOMPLETE_METADATA=True)
def test_incomplete_metadata_rejected_when_flag_enabled():
    """With the flag on, refresh_cache raises IncompleteMetadataError."""
    surface = SurfaceFactory()
    topo = _make_topography(surface, INCOMPLETE_DATAFILE)

    with pytest.raises(IncompleteMetadataError) as excinfo:
        topo.refresh_cache()

    message = str(excinfo.value)
    # The message states the format is supported and lists the missing metadata.
    assert "supported" in message
    assert "physical size" in message
    assert "unit" in message


@pytest.mark.django_db
@override_settings(TOPOBANK_REJECT_INCOMPLETE_METADATA=True)
def test_complete_metadata_accepted_when_flag_enabled():
    """With the flag on, a file with complete metadata is still accepted."""
    surface = SurfaceFactory()
    topo = _make_topography(surface, COMPLETE_DATAFILE)

    topo.refresh_cache()

    assert topo.is_metadata_complete
    assert topo.unit is not None
    assert topo.size_x is not None


@pytest.mark.django_db
@override_settings(TOPOBANK_REJECT_INCOMPLETE_METADATA=True)
def test_incomplete_metadata_surfaced_as_task_error():
    """Via the task machinery, rejection is reported as a task failure with an
    explicit, user-facing error message (and is not re-raised)."""
    surface = SurfaceFactory()
    topo = _make_topography(surface, INCOMPLETE_DATAFILE)

    # run_task swallows IncompleteMetadataError and records it as a task error.
    topo.run_task(_fake_celery_task())

    assert topo.task_state == TaskStateModel.FAILURE
    assert "supported" in topo.task_error
    assert "physical size" in topo.task_error
    assert "unit" in topo.task_error


@pytest.mark.django_db
@override_settings(TOPOBANK_REJECT_INCOMPLETE_METADATA=True)
def test_unsupported_format_error_distinct_from_incomplete_metadata():
    """An unsupported file yields the pre-existing 'unsupported format' error,
    keeping the two failure modes distinct."""
    surface = SurfaceFactory()
    topo = _make_topography(surface, UNSUPPORTED_DATAFILE)

    topo.run_task(_fake_celery_task())

    assert topo.task_state == TaskStateModel.FAILURE
    assert topo.task_error == "The data file is of an unknown or unsupported format."
