import pytest
from rest_framework.reverse import reverse

from topobank.analysis.models import WorkflowResult
from topobank.testing.factories import (
    SurfaceFactory,
    Topography1DFactory,
    TopographyAnalysisFactory,
    UserFactory,
)


@pytest.mark.django_db
def test_refresh_analyses_api(
    api_client, test_analysis_function, django_capture_on_commit_callbacks
):
    """Test whether existing analyses can be renewed by API call."""

    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    topo1 = Topography1DFactory(surface=surface)
    topo2 = Topography1DFactory(surface=surface)

    func = test_analysis_function

    analysis1a = TopographyAnalysisFactory(subject_topography=topo1, function=func)
    analysis2a = TopographyAnalysisFactory(subject_topography=topo2, function=func)

    api_client.force_login(user)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.put(
            reverse("analysis:result-detail", kwargs=dict(pk=analysis1a.pk)),
            format="json",
        )
        assert response.status_code == 201
    assert len(callbacks) == 1

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.put(
            reverse("analysis:result-detail", kwargs=dict(pk=analysis2a.pk)),
            format="json",
        )
        assert response.status_code == 201
    assert len(callbacks) == 1

    #
    # New Analysis objects should be there and marked for the user
    #
    analysis1b = WorkflowResult.objects.get(function=func, subject_dispatch__topography=topo1)
    analysis2b = WorkflowResult.objects.get(function=func, subject_dispatch__topography=topo2)

    assert analysis1b.has_permission(user, "view")
    assert analysis2b.has_permission(user, "view")
