import pytest
from django.shortcuts import reverse
from django.db import transaction

from ...analysis.models import Analysis
from ...analysis.tests.utils import TopographyAnalysisFactory
from ...manager.tests.utils import SurfaceFactory, Topography1DFactory, UserFactory


@pytest.mark.django_db
def test_renew_analyses_api(client, test_analysis_function):
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

        response = client.put(reverse('analysis:result-detail', kwargs=dict(pk=analysis1a.pk)),
                              format='json')  # we need an AJAX request
        assert response.status_code == 201

        response = client.put(reverse('analysis:result-detail', kwargs=dict(pk=analysis2a.pk)),
                              format='json')  # we need an AJAX request
        assert response.status_code == 201

    #
    # Old analyses should be deleted
    #
    with pytest.raises(Analysis.DoesNotExist):
        Analysis.objects.get(id=analysis1a.id)
    with pytest.raises(Analysis.DoesNotExist):
        Analysis.objects.get(id=analysis2a.id)

    #
    # New Analysis objects should be there and marked for the user
    #
    analysis1b = Analysis.objects.get(function=func, subject_dispatch__topography=topo1)
    analysis2b = Analysis.objects.get(function=func, subject_dispatch__topography=topo2)

    assert user in analysis1b.users.all()
    assert user in analysis2b.users.all()
