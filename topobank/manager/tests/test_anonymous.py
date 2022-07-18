import pytest
from django.shortcuts import reverse
from django.core.exceptions import PermissionDenied

from ..utils import selection_from_session, selection_to_instances
from .utils import UserFactory, SurfaceFactory, Topography1DFactory
from topobank.analysis.tests.utils import TopographyAnalysisFactory, AnalysisFunctionFactory
from topobank.analysis.functions import ART_SERIES
from topobank.utils import assert_in_content, assert_not_in_content

#
# The code in these tests rely on a middleware which replaces
# Django's AnonymousUser by the one of django guardian
#


@pytest.mark.django_db
def test_anonymous_user_only_published_as_default(client):
    response = client.get(reverse('manager:select'))
    assert_not_in_content(response, 'All accessible surfaces')
    assert_not_in_content(response, 'Only own surfaces')
    assert_not_in_content(response, 'Only surfaces shared with you')
    assert_in_content(response, 'Only surfaces published by anyone')


@pytest.mark.django_db
def test_anonymous_user_can_see_published(client, handle_usage_statistics, example_authors):
    #
    # publish a surface
    #
    bob = UserFactory(name="Bob")
    surface_name = "Diamond Structure"
    surface = SurfaceFactory(creator=bob, name=surface_name)
    topo = Topography1DFactory(surface=surface)

    pub = surface.publish('cc0-1.0', example_authors)

    # no one is logged in now, assuming the select tab sends a search request
    response = client.get(reverse('manager:search'))

    # should see the published surface
    assert_in_content(response, surface_name)


@pytest.mark.django_db
def test_anonymous_user_can_select_published(client, handle_usage_statistics):
    bob = UserFactory(name="Bob")
    surface_name = "Diamond Structure"
    surface = SurfaceFactory(creator=bob, name=surface_name)
    topo = Topography1DFactory(surface=surface)
    pub = surface.publish('cc0-1.0', bob.name)
    published_surface = pub.surface
    published_topo = published_surface.topography_set.first()

    response = client.post(reverse('manager:topography-select', kwargs=dict(pk=published_topo.pk)))
    assert response.status_code == 200
    sel_topos, sel_surfs, sel_tags = selection_to_instances(selection_from_session(client.session))
    assert len(sel_topos) == 1
    assert published_topo in sel_topos

    response = client.post(reverse('manager:topography-unselect', kwargs=dict(pk=published_topo.pk)))
    assert response.status_code == 200
    sel_topos, sel_surfs, sel_tags = selection_to_instances(selection_from_session(client.session))
    assert len(sel_topos) == 0

    response = client.post(reverse('manager:surface-select', kwargs=dict(pk=published_surface.pk)))
    assert response.status_code == 200
    sel_topos, sel_surfs, sel_tags = selection_to_instances(selection_from_session(client.session))
    assert len(sel_surfs) == 1
    assert published_surface in sel_surfs

    response = client.post(reverse('manager:surface-unselect', kwargs=dict(pk=published_surface.pk)))
    assert response.status_code == 200
    sel_topos, sel_surfs, sel_tags = selection_to_instances(selection_from_session(client.session))
    assert len(sel_surfs) == 0


@pytest.mark.django_db
def test_anonymous_user_cannot_change(client, handle_usage_statistics):

    bob = UserFactory(name="Bob")
    surface_name = "Diamond Structure"
    surface = SurfaceFactory(creator=bob, name=surface_name)
    topo = Topography1DFactory(surface=surface)

    response = client.get(reverse('manager:topography-delete', kwargs=dict(pk=topo.pk)))
    assert response.status_code == 403

    response = client.post(reverse('manager:topography-delete', kwargs=dict(pk=topo.pk)))
    assert response.status_code == 403

    response = client.get(reverse('manager:topography-update', kwargs=dict(pk=topo.pk)))
    assert response.status_code == 403

    response = client.post(reverse('manager:topography-update', kwargs=dict(pk=topo.pk)))
    assert response.status_code == 403

    response = client.get(reverse('manager:surface-delete', kwargs=dict(pk=surface.pk)))
    assert response.status_code == 403

    response = client.post(reverse('manager:surface-delete', kwargs=dict(pk=surface.pk)))
    assert response.status_code == 403

    response = client.get(reverse('manager:surface-update', kwargs=dict(pk=surface.pk)))
    assert response.status_code == 403

    response = client.post(reverse('manager:surface-update', kwargs=dict(pk=surface.pk)))
    assert response.status_code == 403

    response = client.post(reverse('manager:surface-publish', kwargs=dict(pk=surface.pk)))
    assert response.status_code == 403

    response = client.post(reverse('manager:surface-share', kwargs=dict(pk=surface.pk)))
    assert response.status_code == 403


@pytest.mark.django_db
def test_download_analyses_without_permission(client, test_analysis_function, handle_usage_statistics):
    bob = UserFactory()
    surface = SurfaceFactory(creator=bob)
    topo = Topography1DFactory(surface=surface)
    analysis = TopographyAnalysisFactory(subject=topo, function=test_analysis_function)

    response = client.get(reverse('analysis:download',
                                  kwargs=dict(ids=f"{analysis.id}",
                                              art=ART_SERIES,
                                              file_format='txt')))
    assert response.status_code == 403


@pytest.mark.django_db
def test_submit_analyses_without_permission(rf, handle_usage_statistics):
    #
    # This test uses a request factory instead of a client
    # therefore the middleware is not used and we have to
    # set guardian's anonymous user manually.
    # Using the request factory is more lightweight
    # and probably should be used more in tests for Topobank.
    #
    request = rf.post(reverse('analysis:card-submit'),
                      HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    from guardian.utils import get_anonymous_user
    request.user = get_anonymous_user()
    from topobank.analysis.views import submit_analyses_view

    with pytest.raises(PermissionDenied):
        submit_analyses_view(request)



