import pytest
from django.shortcuts import reverse

from .utils import UserFactory, SurfaceFactory, TopographyFactory
from topobank.utils import assert_in_content, assert_not_in_content

@pytest.mark.django_db
def test_anonymous_user_only_published_as_default(client):
    # no one is logged in now, enters select tab
    response = client.get(reverse('manager:select'))
    assert_not_in_content(response, 'All accessible surfaces')
    assert_not_in_content(response, 'Only own surfaces')
    assert_not_in_content(response, 'Only surfaces shared with you')
    assert_in_content(response, 'Only surfaces published by anyone')


@pytest.mark.django_db
def test_anonymous_user_can_see_published(client):
    #
    # publish a surface
    #
    bob = UserFactory(name="Bob")
    surface_name = "Diamond Structure"
    surface = SurfaceFactory(creator=bob, name=surface_name)
    topo = TopographyFactory(surface=surface)
    pub = surface.publish('cc0-1.0')

    # no one is logged in now, assuming the select tab sends a search request
    response = client.get(reverse('manager:search'))

    # should see the published surface
    assert_in_content(response, surface_name)


