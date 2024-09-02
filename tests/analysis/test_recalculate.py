import pytest
from django.db import transaction
from django.shortcuts import reverse

from topobank.analysis.models import Analysis
from topobank.testing.factories import (
    SurfaceFactory,
    Topography1DFactory,
    TopographyAnalysisFactory,
    UserFactory,
)


@pytest.mark.django_db
def test_refresh_analyses_api(client, test_analysis_function):
    """Test whether existing analyses can be renewed by API call."""

    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    topo1 = Topography1DFactory(surface=surface)
    topo2 = Topography1DFactory(surface=surface)

    func = test_analysis_function

    analysis1a = TopographyAnalysisFactory(subject_topography=topo1, function=func)
    analysis2a = TopographyAnalysisFactory(subject_topography=topo2, function=func)

    client.force_login(user)

    with transaction.atomic():
        # trigger "renew" for two specific analyses

        response = client.put(
            reverse("analysis:result-detail", kwargs=dict(pk=analysis1a.pk)),
            format="json",
        )  # we need an AJAX request
        assert response.status_code == 201

        response = client.put(
            reverse("analysis:result-detail", kwargs=dict(pk=analysis2a.pk)),
            format="json",
        )  # we need an AJAX request
        assert response.status_code == 201

    #
    # New Analysis objects should be there and marked for the user
    #
    analysis1b = Analysis.objects.get(function=func, subject_dispatch__topography=topo1)
    analysis2b = Analysis.objects.get(function=func, subject_dispatch__topography=topo2)

    assert analysis1b.has_permission(user, "view")
    assert analysis2b.has_permission(user, "view")
