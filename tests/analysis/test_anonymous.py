import pytest
from django.shortcuts import reverse

from topobank.testing.factories import (
    SurfaceFactory,
    Topography1DFactory,
    TopographyAnalysisFactory,
    UserFactory,
)

#
# The code in these supplib rely on a middleware which replaces
# Django's AnonymousUser by the one of django guardian
#


@pytest.mark.django_db
def test_download_analyses_without_permission(
    api_client, test_analysis_function, handle_usage_statistics
):
    bob = UserFactory()
    surface = SurfaceFactory(created_by=bob)
    topo = Topography1DFactory(surface=surface)
    analysis = TopographyAnalysisFactory(
        subject_topography=topo, function=test_analysis_function
    )

    response = api_client.get(
        reverse(
            "analysis:download", kwargs=dict(ids=f"{analysis.id}", file_format="txt")
        )
    )
    assert response.status_code == 404
