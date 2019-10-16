import pytest
import json
from collections import OrderedDict
from operator import itemgetter

from django.shortcuts import reverse
from rest_framework.test import APIRequestFactory

from ..views import select_surface, unselect_surface, SurfaceSearch, select_topography, unselect_topography
from ..utils import selected_instances
from .utils import SurfaceFactory, UserFactory, TopographyFactory


@pytest.mark.django_db
def test_select_surface():
    user = UserFactory()
    surface1 = SurfaceFactory(creator=user)
    surface2 = SurfaceFactory(creator=user)

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
def test_select_topography():
    user = UserFactory()
    surface1 = SurfaceFactory(creator=user)
    topo1a = TopographyFactory(surface=surface1)
    topo1b = TopographyFactory(surface=surface1)
    topo1c = TopographyFactory(surface=surface1)
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
    # When selecting all topographies of a surface, the surface should be selected
    #
    request = factory.post(reverse('manager:topography-select', kwargs=dict(pk=topo1c.pk)))
    request.user = user
    request.session = session

    response = select_topography(request, topo1c.pk)

    assert response.status_code == 200

    assert sorted(request.session['selection']) == [f'surface-{surface1.pk}']

    assert selected_instances(request)[1] == [surface1]


@pytest.mark.django_db
def test_unselect_topography():
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


def ordereddict_to_dict(input_ordered_dict, sorted_by='pk'):
    result = json.loads(json.dumps(input_ordered_dict))
    if sorted_by is not None:
        result = sorted(result, key=itemgetter(sorted_by))
    return result


@pytest.mark.django_db
def test_surface_search_with_request_factory():
    #
    # Create some database objects
    #
    user = UserFactory()
    surface1 = SurfaceFactory(creator=user)
    surface2 = SurfaceFactory(creator=user)
    surface3 = SurfaceFactory(creator=user)

    topo1a = TopographyFactory(surface=surface1)
    topo1b = TopographyFactory(surface=surface1)
    topo2a = TopographyFactory(surface=surface2)
    topo2b = TopographyFactory(surface=surface2)
    # no topography for surface3 on purpose

    #
    # Set some tags
    #
    surface1.tags = ['bike', 'train/tgv']
    surface1.save()
    topo2a.tags = ['bike', 'train/ice']
    topo2a.save()

    #
    # Fix a selection and create a request with this selection
    #
    session = dict(selection=[f'surface-{surface2.pk}', f'topography-{topo1a.pk}', f'surface-{surface3.pk}'])

    factory = APIRequestFactory()
    request = factory.get(reverse('manager:surface-search'))
    request.user = user
    request.session = session

    #
    # Create search response and compare with expectation
    #
    response = SurfaceSearch.as_view()(request)

    assert response.status_code == 200

    user_url = request.build_absolute_uri(user.get_absolute_url())

    surface1_prefix = f"/manager/surface/{surface1.pk}/"
    topo1a_prefix = f"/manager/topography/{topo1a.pk}/"
    topo1b_prefix = f"/manager/topography/{topo1b.pk}/"

    surface2_prefix = f"/manager/surface/{surface2.pk}/"
    topo2a_prefix = f"/manager/topography/{topo2a.pk}/"
    topo2b_prefix = f"/manager/topography/{topo2b.pk}/"

    surface3_prefix = f"/manager/surface/{surface3.pk}/"

    expected_dicts = [
        {
            'category': None,
            'children': [
                {'creator': user_url,
                 'description': '',
                 'folder': False,
                 'key': f'topography-{topo1a.pk}',
                 'name': topo1a.name,
                 'pk': topo1a.pk,
                 'selected': True,
                 'tags': [],
                 'title': topo1a.name,
                 'urls': {'delete': topo1a_prefix + 'delete/',
                          'detail': topo1a_prefix,
                          'select': topo1a_prefix + 'select/',
                          'show_analyses': topo1a_prefix + 'show-analyses/',
                          'unselect': topo1a_prefix + 'unselect/',
                          'update': topo1a_prefix + 'update/'}},
                {'creator': user_url,
                 'description': '',
                 'folder': False,
                 'key': f'topography-{topo1b.pk}',
                 'name': topo1b.name,
                 'pk': topo1b.pk,
                 'selected': False,
                 'tags': [],
                 'title': topo1b.name,
                 'urls': {'delete': topo1b_prefix + 'delete/',
                          'detail': topo1b_prefix,
                          'select': topo1b_prefix + 'select/',
                          'show_analyses': topo1b_prefix + 'show-analyses/',
                          'unselect': topo1b_prefix + 'unselect/',
                          'update': topo1b_prefix + 'update/'}},

            ],
            'creator': user_url,
            'description': '',
            'folder': True,
            'key': f'surface-{surface1.pk}',
            'name': surface1.name,
            'pk': surface1.pk,
            'selected': False,
            'sharing_status': 'own',
            'tags': ['bike', 'train/tgv'],
            'title': surface1.name,
            'urls': {'add_topography': surface1_prefix + 'new-topography/',
                     'delete': surface1_prefix + 'delete/',
                     'detail': surface1_prefix,
                     'download': surface1_prefix + 'download/',
                     'select': surface1_prefix + 'select/',
                     'share': surface1_prefix + 'share/',
                     'show_analyses': surface1_prefix + 'show-analyses/',
                     'unselect': surface1_prefix + 'unselect/',
                     'update': surface1_prefix + 'update/'}
        },
        {
            'category': None,
            'children': [
                {'creator': user_url,
                 'description': '',
                 'folder': False,
                 'key': f'topography-{topo2a.pk}',
                 'name': topo2a.name,
                 'pk': topo2a.pk,
                 'selected': True,
                 'tags': ['bike', 'train/ice'],
                 'title': topo2a.name,
                 'urls': {'delete': topo2a_prefix + 'delete/',
                          'detail': topo2a_prefix,
                          'select': topo2a_prefix + 'select/',
                          'show_analyses': topo2a_prefix + 'show-analyses/',
                          'unselect': topo2a_prefix + 'unselect/',
                          'update': topo2a_prefix + 'update/'}},
                {'creator': user_url,
                 'description': '',
                 'folder': False,
                 'key': f'topography-{topo2b.pk}',
                 'name': topo2b.name,
                 'pk': topo2b.pk,
                 'selected': True,
                 'tags': [],
                 'title': topo2b.name,
                 'urls': {'delete': topo2b_prefix + 'delete/',
                          'detail': topo2b_prefix,
                          'select': topo2b_prefix + 'select/',
                          'show_analyses': topo2b_prefix + 'show-analyses/',
                          'unselect': topo2b_prefix + 'unselect/',
                          'update': topo2b_prefix + 'update/'}},

            ],
            'creator': user_url,
            'description': '',
            'folder': True,
            'key': f'surface-{surface2.pk}',
            'name': surface2.name,
            'pk': surface2.pk,
            'selected': True,
            'sharing_status': 'own',
            'tags': [],
            'title': surface2.name,
            'urls': {'add_topography': surface2_prefix + 'new-topography/',
                     'delete': surface2_prefix + 'delete/',
                     'detail': surface2_prefix,
                     'download': surface2_prefix + 'download/',
                     'select': surface2_prefix + 'select/',
                     'share': surface2_prefix + 'share/',
                     'show_analyses': surface2_prefix + 'show-analyses/',
                     'unselect': surface2_prefix + 'unselect/',
                     'update': surface2_prefix + 'update/'}
        },
        {
            'category': None,
            'children': [],
            'creator': user_url,
            'description': '',
            'folder': True,
            'key': f'surface-{surface3.pk}',
            'name': surface3.name,
            'pk': surface3.pk,
            'selected': True,
            'sharing_status': 'own',
            'tags': [],
            'title': surface3.name,
            'urls': {'add_topography': surface3_prefix + 'new-topography/',
                     'delete': surface3_prefix + 'delete/',
                     'detail': surface3_prefix,
                     # 'download': surface3_prefix + 'download/', # this should be missing, because no topographies yet
                     'select': surface3_prefix + 'select/',
                     'share': surface3_prefix + 'share/',
                     # 'show_analyses': surface3_prefix + 'show-analyses/', # this should be missing
                     'unselect': surface3_prefix + 'unselect/',
                     'update': surface3_prefix + 'update/'}
        },
    ]

    assert ordereddict_to_dict(response.data) == expected_dicts
