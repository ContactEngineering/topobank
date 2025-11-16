"""
Tests related to thumbnails.
"""

import pytest
from django.shortcuts import reverse

from topobank.manager.models import Topography
from topobank.testing.factories import (
    SurfaceFactory,
    Topography1DFactory,
    Topography2DFactory,
    UserFactory,
)


@pytest.mark.django_db
def test_thumbnail_exists_for_new_topography():
    topo = Topography2DFactory(size_x=1, size_y=1)
    topo.refresh_cache()
    # should have a thumbnail picture
    assert topo.thumbnail is not None


@pytest.mark.django_db
def test_thumbnail_creation_fails(mocker):
    topo = Topography2DFactory(size_x=1, size_y=1)
    topo.refresh_cache()
    # should have a thumbnail picture
    assert topo.thumbnail is not None

    mocker.patch(
        "topobank.manager.models.Topography._make_thumbnail",
        side_effect=Exception("Test exception"),
    )
    topo.refresh_cache()
    # should have no thumbnail picture
    assert topo.thumbnail is None


@pytest.mark.django_db
def test_renewal_on_topography_detrend_mode_change(
    api_client, mocker, settings, django_capture_on_commit_callbacks
):
    """Check whether thumbnail is renewed if detrend mode changes for a topography"""
    refresh_cache_mock = mocker.patch(
        "topobank.manager.models.Topography.refresh_cache"
    )

    user = UserFactory()
    surface = SurfaceFactory(created_by=user)
    topo = Topography1DFactory(surface=surface, size_y=1, detrend_mode="center")

    api_client.force_login(user)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.patch(
            reverse("manager:topography-api-detail", kwargs=dict(pk=topo.pk)),
            {
                "data_source": 0,
                "name": topo.name,
                "measurement_date": topo.measurement_date,
                "description": "something",
                "height_scale": 1.0,
                "detrend_mode": "height",
                "instrument_type": Topography.INSTRUMENT_TYPE_UNDEFINED,
                "has_undefined_data": False,
                "fill_undefined_data_mode": Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING,
            },
        )

    # we just check here that the form is filled completely, otherwise the thumbnail would not be recreated too
    assert response.status_code == 200, response.content
    assert len(callbacks) == 1  # single callback for cache renewal
    assert refresh_cache_mock.called


@pytest.mark.django_db
def test_no_renewal_on_measurement_date_change(
    api_client,
    mocker,
    settings,
    django_capture_on_commit_callbacks,
    handle_usage_statistics,
):
    """Check whether thumbnail is renewed if detrend mode changes for a topography"""
    settings.CELERY_TASK_ALWAYS_EAGER = True

    refresh_cache_mock = mocker.patch(
        "topobank.manager.models.Topography.refresh_cache"
    )

    user = UserFactory()
    surface = SurfaceFactory(created_by=user)
    topo = Topography1DFactory(surface=surface, size_y=1, detrend_mode="center")

    api_client.force_login(user)

    refresh_cache_mock.reset_mock()

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.patch(
            reverse("manager:topography-api-detail", kwargs=dict(pk=topo.pk)),
            {
                "measurement_date": topo.measurement_date,
            },
        )

    # we just check here that the form is filled completely, otherwise the thumbnail would not be recreated too
    assert response.status_code == 200, response.content
    assert len(callbacks) == 0  # no callback
    assert not refresh_cache_mock.called
