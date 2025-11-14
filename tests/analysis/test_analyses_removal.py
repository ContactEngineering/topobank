"""
Test whether analyses are recalculated on certain events.
"""

import pytest
from django.shortcuts import reverse

from topobank.analysis.models import WorkflowResult
from topobank.manager.models import Topography
from topobank.testing.factories import (
    SurfaceAnalysisFactory,
    SurfaceFactory,
    Topography1DFactory,
    Topography2DFactory,
    TopographyAnalysisFactory,
    UserFactory,
)


@pytest.mark.parametrize(
    "changed_values_dict,response_code",
    [  # would should be changed in POST request (->str values!)
        ({"size_y": "100"}, 200),
        (
            {
                "height_scale": "10",
                "instrument_type": "microscope-based",
            },
            200,
        ),
        # renew_squeezed should be called because of height_scale, not because of instrument_type
        (
            {
                "instrument_type": "microscope-based",  # instrument type changed at least
                "instrument_parameters": {"resolution": {"value": 1.0, "unit": "mm"}},
            },
            200,
        ),
        (
            {
                "instrument_parameters": {"tip_radius": {"value": 2, "unit": "nm"}},
            },
            200,
        ),
        (
            {
                "instrument_parameters": {"tip_radius": {"unit": "nm"}},
            },
            400,  # value is missing
        ),
    ],
)
@pytest.mark.django_db
def test_analysis_removal_on_topography_change(
    api_client,
    django_capture_on_commit_callbacks,
    test_analysis_function,
    handle_usage_statistics,
    changed_values_dict,
    response_code,
):
    """Check whether methods for renewal are called on significant topography change."""

    user = UserFactory()
    surface = SurfaceFactory(created_by=user)
    topo = Topography2DFactory(
        surface=surface,
        size_x=1,
        size_y=1,
        size_editable=True,
        instrument_type=Topography.INSTRUMENT_TYPE_CONTACT_BASED,
        instrument_parameters={"tip_radius": {"value": 1.0, "unit": "mm"}},
    )
    TopographyAnalysisFactory(subject_topography=topo, function=test_analysis_function)

    assert WorkflowResult.objects.filter(subject_dispatch__topography=topo).count() == 1

    api_client.force_login(user)

    initial_data_for_post = {
        "data_source": topo.data_source,
        "description": topo.description,
        "name": topo.name,
        "size_x": topo.size_x,
        "size_y": topo.size_y,
        "height_scale": topo.height_scale,
        "detrend_mode": "center",
        "measurement_date": format(topo.measurement_date, "%Y-%m-%d"),
        "tags": [],
        "instrument_name": "",
        "instrument_type": topo.instrument_type,
        "instrument_parameters": {"tip_radius": {"value": 1.0, "unit": "mm"}},
        "fill_undefined_data_mode": Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING,
        "has_undefined_data": False,
    }
    changed_data_for_post = initial_data_for_post.copy()

    # Update data
    changed_data_for_post.update(changed_values_dict)  # here is a change at least

    # If we post the initial data, nothing should have been changed, so no actions
    # should be triggered
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.patch(
            reverse("manager:topography-api-detail", kwargs=dict(pk=topo.pk)),
            initial_data_for_post,
        )
    assert response.status_code == 200

    assert len(callbacks) == 0
    # Nothing changed, so no callbacks

    # Check that analysis still exists
    assert WorkflowResult.objects.filter(subject_dispatch__topography=topo).count() == 1

    #
    # Now we post the changed data, some action (=callbacks) should be triggered
    #
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.patch(
            reverse("manager:topography-api-detail", kwargs=dict(pk=topo.pk)),
            changed_data_for_post,
        )
    assert response.status_code == response_code, response.content

    assert len(callbacks) == (1 if response_code == 200 else 0)

    # Check that the analysis has been deprecated
    if response_code == 200:
        assert (
            WorkflowResult.objects.filter(
                subject_dispatch__topography=topo, deprecation_time__isnull=False
            ).count()
            == 1
        )


@pytest.mark.django_db
def test_analysis_removal_on_topography_deletion(
    api_client, test_analysis_function, handle_usage_statistics
):
    """Check whether surface analyses are deleted if topography is deleted."""

    user = UserFactory()
    surface = SurfaceFactory(created_by=user)
    topo = Topography1DFactory(surface=surface, created_by=user)

    TopographyAnalysisFactory(subject_topography=topo, function=test_analysis_function, created_by=user)
    SurfaceAnalysisFactory(subject_surface=surface, function=test_analysis_function, created_by=user)
    SurfaceAnalysisFactory(subject_surface=surface, function=test_analysis_function, created_by=user)

    assert (
        WorkflowResult.objects.filter(subject_dispatch__topography=topo.id).count() == 1
    )
    assert (
        WorkflowResult.objects.filter(subject_dispatch__surface=surface.id).count() == 2
    )

    assert surface.topography_set.count() == 1

    #
    # Now remove topography and see whether all analyses are deleted
    #
    api_client.force_login(user)

    response = api_client.delete(
        reverse("manager:topography-api-detail", kwargs=dict(pk=topo.pk))
    )

    assert response.status_code == 204

    assert surface.topography_set.count() == 0

    # No more topography analyses left
    assert WorkflowResult.objects.filter(subject_dispatch__topography=topo).count() == 0

    # No more surface analyses left, because the surface no longer has topographies
    # The analysis of the surface is not deleting in this test, because the analysis
    # does not actually run. (Analysis run `on_commit`, but this is never triggered in
    # this test.)
    # assert Analysis.objects.filter(subject_dispatch__surface=surface).count() == 0
