"""Test related to Find&elect tab except of searching"""

import pytest

from django.shortcuts import reverse
from rest_framework.test import APIRequestFactory

from ..views import select_surface, unselect_surface, \
    select_topography, unselect_topography, \
    select_tag, unselect_tag, unselect_all, DEFAULT_SELECT_TAB_STATE
from ..utils import selected_instances
from .utils import SurfaceFactory, UserFactory, Topography1DFactory, \
    TagModelFactory
from topobank.utils import assert_no_form_errors


@pytest.mark.django_db
def test_select_surface():
    user = UserFactory()
    surface1 = SurfaceFactory(creator=user)
    surface2 = SurfaceFactory(creator=user)
    surface3 = SurfaceFactory(creator=user)
    topo3a = Topography1DFactory(surface=surface3)
    topo3b = Topography1DFactory(surface=surface3)

    factory = APIRequestFactory()
    session = {}

    #
    # First select a single surface
    #
    request = factory.post(reverse('manager:surface-select', kwargs=dict(pk=surface1.pk)))
    request.user = user
    request.session = session

    response = select_surface(request, surface1.pk)

    assert response.status_code == 200

    assert request.session['selection'] == [f'surface-{surface1.pk}']

    assert selected_instances(request)[1] == [surface1]

    #
    # Then select another
    #
    request = factory.post(reverse('manager:surface-select', kwargs=dict(pk=surface1.pk)))
    request.user = user
    request.session = session

    response = select_surface(request, surface2.pk)

    assert response.status_code == 200

    assert sorted(request.session['selection']) == [f'surface-{surface1.pk}', f'surface-{surface2.pk}']

    assert selected_instances(request)[1] == [surface1, surface2]

    #
    # If a surface is selected after a single topography of this surface
    # was selected, the selection of the single topography should be still there
    #
    request = factory.post(reverse('manager:topography-select', kwargs=dict(pk=topo3a.pk)))
    request.user = user
    request.session = session

    response = select_topography(request, topo3a.pk)

    assert response.status_code == 200

    assert sorted(request.session['selection']) == [f'surface-{surface1.pk}', f'surface-{surface2.pk}',
                                                    f'topography-{topo3a.pk}']

    assert selected_instances(request)[0] == [topo3a]
    assert selected_instances(request)[1] == [surface1, surface2]

    request = factory.post(reverse('manager:surface-select', kwargs=dict(pk=surface3.pk)))
    request.user = user
    request.session = session

    response = select_surface(request, surface3.pk)

    assert response.status_code == 200

    # the selection for the single topography should still be present
    assert sorted(request.session['selection']) == [f'surface-{surface1.pk}', f'surface-{surface2.pk}',
                                                    f'surface-{surface3.pk}', f'topography-{topo3a.pk}']

    assert selected_instances(request)[0] == [topo3a]
    assert selected_instances(request)[1] == [surface1, surface2, surface3]


@pytest.mark.django_db
def test_unselect_surface():
    user = UserFactory()
    surface1 = SurfaceFactory(creator=user)
    surface2 = SurfaceFactory(creator=user)

    factory = APIRequestFactory()
    session = dict(selection=[f'surface-{surface1.pk}', f'surface-{surface2.pk}'])

    #
    # deselect a surface
    #
    request = factory.post(reverse('manager:surface-unselect', kwargs=dict(pk=surface1.pk)))
    request.user = user
    request.session = session

    response = unselect_surface(request, surface1.pk)

    assert response.status_code == 200

    assert request.session['selection'] == [f'surface-{surface2.pk}']

    assert selected_instances(request)[1] == [surface2]


@pytest.mark.django_db
def test_try_to_select_surface_but_not_allowed():
    user1 = UserFactory()
    user2 = UserFactory()
    surface1 = SurfaceFactory(creator=user1)


    factory = APIRequestFactory()
    session = {}

    request = factory.post(reverse('manager:surface-select', kwargs=dict(pk=surface1.pk)))
    request.user = user2
    request.session = session

    response = select_surface(request, surface1.pk)

    assert response.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_try_to_select_topography_but_not_allowed():
    user1 = UserFactory()
    user2 = UserFactory()
    surface1 = SurfaceFactory(creator=user1)
    topo1 = Topography1DFactory(surface=surface1)

    factory = APIRequestFactory()
    session = {}

    request = factory.post(reverse('manager:topography-select', kwargs=dict(pk=topo1.pk)))
    request.user = user2
    request.session = session

    response = select_topography(request, topo1.pk)

    assert response.status_code == 403

    # if user 1 shares the surface with user 2, it is allowed
    surface1.share(user2)
    response = select_topography(request, topo1.pk)
    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_try_to_select_tag_but_not_allowed():
    user1 = UserFactory()
    user2 = UserFactory()

    tag1 = TagModelFactory()
    surface1 = SurfaceFactory(creator=user1, tags=[tag1])

    factory = APIRequestFactory()
    session = {}

    request = factory.post(reverse('manager:tag-select', kwargs=dict(pk=tag1.pk)))
    request.user = user2
    request.session = session

    response = select_tag(request, tag1.pk)

    # not allowed, because tag is not used by user 2
    assert response.status_code == 403

    # If user 2 also uses this tag, it can be selected
    surface2 = SurfaceFactory(creator=user2, tags=[tag1])

    response = select_tag(request, tag1.pk)
    assert response.status_code == 200


@pytest.mark.django_db
def test_select_topography():
    user = UserFactory()
    surface1 = SurfaceFactory(creator=user)
    topo1a = Topography1DFactory(surface=surface1)
    topo1b = Topography1DFactory(surface=surface1)
    topo1c = Topography1DFactory(surface=surface1)
    surface2 = SurfaceFactory(creator=user)

    factory = APIRequestFactory()
    session = {}

    #
    # First select a single surface
    #
    request = factory.post(reverse('manager:topography-select', kwargs=dict(pk=topo1a.pk)))
    request.user = user
    request.session = session

    response = select_topography(request, topo1a.pk)

    assert response.status_code == 200

    assert request.session['selection'] == [f'topography-{topo1a.pk}']

    assert selected_instances(request)[0] == [topo1a]

    #
    # Then select a second one
    #
    request = factory.post(reverse('manager:topography-select', kwargs=dict(pk=topo1b.pk)))
    request.user = user
    request.session = session

    response = select_topography(request, topo1b.pk)

    assert response.status_code == 200

    assert sorted(request.session['selection']) == [f'topography-{topo1a.pk}', f'topography-{topo1b.pk}']

    assert selected_instances(request)[0] == [topo1a, topo1b]

    #
    # When selecting all topographies of a surface, the surface should not be selected
    #
    request = factory.post(reverse('manager:topography-select', kwargs=dict(pk=topo1c.pk)))
    request.user = user
    request.session = session

    response = select_topography(request, topo1c.pk)

    assert response.status_code == 200

    assert sorted(request.session['selection']) == [f'topography-{topo1a.pk}', f'topography-{topo1b.pk}',
                                                    f'topography-{topo1c.pk}']

    assert selected_instances(request)[0] == [topo1a, topo1b, topo1c]

    assert selected_instances(request)[1] == []  # we only want explicitly selected objects now

    #
    # When selecting some arbitrary topography, a permission denied should show up
    #
    invalid_pk = 99999999999
    request = factory.post(reverse('manager:topography-select', kwargs=dict(pk=invalid_pk)))
    request.user = user
    request.session = session

    response = select_topography(request, invalid_pk)

    assert response.status_code == 403


@pytest.mark.django_db
def test_unselect_topography():
    user = UserFactory()
    surface1 = SurfaceFactory(creator=user)
    topo1a = Topography1DFactory(surface=surface1)
    topo1b = Topography1DFactory(surface=surface1)
    surface2 = SurfaceFactory(creator=user)

    factory = APIRequestFactory()
    session = dict(selection=[f'surface-{surface1.pk}', f'surface-{surface2.pk}', f'topography-{topo1b.pk}'])

    #
    # deselect a topography
    #
    request = factory.post(reverse('manager:topography-unselect', kwargs=dict(pk=topo1a.pk)))
    request.user = user
    request.session = session

    response = unselect_topography(request, topo1a.pk)

    assert response.status_code == 200

    # This has no effect, since the topography was not explicitly selected
    assert sorted(request.session['selection']) == sorted([f'surface-{surface1.pk}', f'surface-{surface2.pk}',
                                                           f'topography-{topo1b.pk}'])

    assert selected_instances(request)[0] == [topo1b]
    assert selected_instances(request)[1] == [surface1, surface2]

    #
    # Now remove topo1b
    #
    request = factory.post(reverse('manager:topography-unselect', kwargs=dict(pk=topo1b.pk)))
    request.user = user
    request.session = session

    response = unselect_topography(request, topo1b.pk)

    assert response.status_code == 200
    assert sorted(request.session['selection']) == [f'surface-{surface1.pk}', f'surface-{surface2.pk}']
    assert selected_instances(request)[0] == []
    assert selected_instances(request)[1] == [surface1, surface2]


#
# Tests for selection of tags
#
@pytest.mark.django_db
def test_select_tag():

    user = UserFactory()

    tag1 = TagModelFactory()
    tag2 = TagModelFactory()

    # we use the tags, so the user is allowed to select it
    surface1 = SurfaceFactory(creator=user, tags=[tag1, tag2])

    factory = APIRequestFactory()
    session = {}

    #
    # First select a single tag
    #
    request = factory.post(reverse('manager:tag-select', kwargs=dict(pk=tag1.pk)))
    request.user = user
    request.session = session

    response = select_tag(request, tag1.pk)

    assert response.status_code == 200

    assert request.session['selection'] == [f'tag-{tag1.pk}']

    assert selected_instances(request)[2] == [tag1]

    #
    # Then select another
    #
    request = factory.post(reverse('manager:tag-select', kwargs=dict(pk=tag2.pk)))
    request.user = user
    request.session = session

    response = select_tag(request, tag2.pk)

    assert response.status_code == 200

    assert sorted(request.session['selection']) == [f'tag-{tag1.pk}', f'tag-{tag2.pk}']

    assert selected_instances(request)[2] == [tag1, tag2]


@pytest.mark.django_db
def test_unselect_tag():
    user = UserFactory()

    tag1 = TagModelFactory()
    tag2 = TagModelFactory()

    # we use the tags, so the user is allowed to select it
    surface1 = SurfaceFactory(creator=user, tags=[tag1, tag2])

    factory = APIRequestFactory()
    session = dict(selection=[f'tag-{tag1.pk}', f'tag-{tag2.pk}'])

    #
    # deselect a tag
    #
    request = factory.post(reverse('manager:tag-unselect', kwargs=dict(pk=tag1.pk)))
    request.user = user
    request.session = session

    response = unselect_tag(request, tag1.pk)

    assert response.status_code == 200

    assert request.session['selection'] == [f'tag-{tag2.pk}']

    assert selected_instances(request)[2] == [tag2]


@pytest.mark.django_db
def test_unselect_all():
    user = UserFactory()

    tag1 = TagModelFactory()

    # we use the tags, so the user is allowed to select it
    surface1 = SurfaceFactory(creator=user, tags=[tag1])
    topo1 = Topography1DFactory(surface=surface1)

    factory = APIRequestFactory()
    session = dict(selection=[f'tag-{tag1.pk}', f'surface-{surface1.pk}', f'topography-{topo1.pk}'])

    #
    # deselect all
    #
    request = factory.post(reverse('manager:unselect-all'))
    request.user = user
    request.session = session

    response = unselect_all(request)

    assert response.status_code == 200

    assert request.session['selection'] == []


@pytest.mark.django_db
def test_select_tab_state_should_be_default_after_login(client):

    # first request the site anonymously .. select tab state is set to that of
    # an anonymous user
    response = client.get(reverse('manager:select'))
    assert response.context['select_tab_state']['sharing_status'] == 'published_ingress'

    # Then login as authenticated user
    password = "abcd"
    user = UserFactory(password=password)

    # we use a real request in order to trigger the signal
    response = client.post(reverse('account_login'), {
        'password': password,
        'login': user.username,
    })

    assert response.status_code == 302
    assert_no_form_errors(response)

    response = client.get(reverse('manager:select'))

    assert response.context['select_tab_state'] == DEFAULT_SELECT_TAB_STATE


@pytest.mark.django_db
def test_select_tab_state_should_be_default_after_search(client, handle_usage_statistics):

    state_before_search = DEFAULT_SELECT_TAB_STATE.copy()
    state_before_search['current_page'] = 2

    user = UserFactory()
    client.force_login(user)
    client.session['select_tab_state'] = state_before_search

    response = client.get(reverse('search'), data={'search': 'what I want to find'}, follow=True)

    exp_state_after_search = DEFAULT_SELECT_TAB_STATE.copy()
    exp_state_after_search['search_term'] = 'what I want to find'

    assert exp_state_after_search['current_page'] == 1

    assert response.context['select_tab_state'] == exp_state_after_search









