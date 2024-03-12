from django.urls import reverse

from topobank.analysis.models import AnalysisFunction
from topobank.analysis.tests.utils import SurfaceAnalysisFactory, TopographyAnalysisFactory
from topobank.manager.tests.utils import SurfaceFactory, Topography1DFactory
from topobank.users.tests.factories import UserFactory


def test_statistics(api_client, handle_usage_statistics):
    user = UserFactory()
    surf1 = SurfaceFactory(creator=user)
    surf2 = SurfaceFactory(creator=user)
    topo1a = Topography1DFactory(surface=surf1)
    topo1b = Topography1DFactory(surface=surf1)
    topo2a = Topography1DFactory(surface=surf2)

    func = AnalysisFunction.objects.get(name="test")

    #
    # Generate analyses for topographies with differing arguments
    #
    kwargs_1a = dict(a=1, b=2)
    kwargs_1b = dict(a=1, b=3)  # differing from kwargs_1a!
    TopographyAnalysisFactory(subject_topography=topo1a, function=func, kwargs=kwargs_1a)
    TopographyAnalysisFactory(subject_topography=topo1b, function=func, kwargs=kwargs_1b)
    TopographyAnalysisFactory(subject_topography=topo2a, function=func)  # default arguments

    #
    # Generate analyses for surfaces with differing arguments
    #
    kwargs_1 = dict(a=2, b=2)
    kwargs_2 = dict(a=2, b=3)  # differing from kwargs_1a!
    SurfaceAnalysisFactory(subject_surface=surf1, function=func, kwargs=kwargs_1)
    SurfaceAnalysisFactory(subject_surface=surf2, function=func, kwargs=kwargs_2)

    response = api_client.get(reverse('manager:statistics'))
    assert response.data['nb_users'] == 2
    assert response.data['nb_surfaces'] == 2
    assert response.data['nb_topographies'] == 3

    response = api_client.get(reverse('analysis:statistics'))
    assert response.data['nb_analyses'] == 5
