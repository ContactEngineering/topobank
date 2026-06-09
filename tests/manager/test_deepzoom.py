import logging

import pytest

from topobank.testing.factories import Topography2DFactory


@pytest.mark.django_db
def test_deepzoom_creation_fails(mocker):
    topo = Topography2DFactory(size_x=1, size_y=1)
    topo.refresh_cache()
    # should have a deepzoom images
    assert topo.deepzoom is not None

    mocker.patch(
        "topobank.manager.models.Topography._make_deepzoom",
        side_effect=Exception("Test exception"),
    )
    topo.refresh_cache()
    # should have no deepzoom images
    assert topo.deepzoom is None


@pytest.mark.django_db
def test_missing_thumbnail_is_logged_but_not_fatal(mocker, caplog):
    """A failed thumbnail stays non-fatal but is surfaced via an ERROR log."""
    topo = Topography2DFactory(size_x=1, size_y=1)

    mocker.patch(
        "topobank.manager.models.Topography._make_thumbnail",
        side_effect=Exception("Test exception"),
    )

    with caplog.at_level(logging.ERROR, logger="topobank.manager.models"):
        topo.refresh_cache()  # must not raise

    # Generation stayed resilient: thumbnail cleared, no exception propagated.
    assert topo.thumbnail is None
    # ...but the failure is now observable: both the make_thumbnail handler and
    # the end-of-refresh verification block log at ERROR mentioning "thumbnail".
    assert any(
        record.levelno == logging.ERROR and "thumbnail" in record.getMessage()
        for record in caplog.records
    )
    assert any(
        "missing derived files" in record.getMessage() for record in caplog.records
    )
