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

    assert selected_instances(request)[1] == [ surface1 ]

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

    assert selected_instances(request)[0] == [ topo1a ]

    #
    # Then select another
    #
    request = factory.post(reverse('manager:topography-select', kwargs=dict(pk=topo1b.pk)))
    request.user = user
    request.session = session

    response = select_topography(request, topo1b.pk)

    assert response.status_code == 200

    assert sorted(request.session['selection']) == [f'topography-{topo1a.pk}', f'topography-{topo1b.pk}']

    assert selected_instances(request)[0] == [topo1a, topo1b]


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

    user = UserFactory()
    surface1 = SurfaceFactory(creator=user)
    surface2 = SurfaceFactory(creator=user)
    surface3 = SurfaceFactory(creator=user)

    topo1a = TopographyFactory(surface=surface1)
    topo1b = TopographyFactory(surface=surface1)
    topo2a = TopographyFactory(surface=surface2)
    topo2b = TopographyFactory(surface=surface2)

    factory = APIRequestFactory()
    session = dict(selection=[f'surface-{surface2.pk}', f'topography-{topo1a.pk}', f'surface-{surface3.pk}'])

    request = factory.get(reverse('manager:surface-search'))
    request.user = user
    request.session = session

    response = SurfaceSearch.as_view()(request)

    assert response.status_code == 200

    user_url = request.build_absolute_uri(user.get_absolute_url())

    expected_dicts = [
        {
            'pk': surface1.pk,
            'name': surface1.name,
            'creator': user_url,
            'description': surface1.description,
            'category': surface1.category,
            'topographies': [
                {
                    'pk': topo1a.pk,
                    'name': topo1a.name,
                    'creator': user_url,
                    'description': topo1a.description,
                    'is_selected': True
                },
                {
                    'pk': topo1b.pk,
                    'name': topo1b.name,
                    'creator': user_url,
                    'description': topo1b.description,
                    'is_selected': False}
            ],
            'select_url': '/manager/surface/1/select/',
            'unselect_url': '/manager/surface/1/unselect/',
            'is_selected': False
        },
        {
            'pk': surface2.pk,
            'name': surface2.name,
            'creator': user_url,
            'description': surface2.description,
            'category': surface2.category,
            'topographies': [
                {
                    'pk': topo2a.pk,
                    'name': topo2a.name,
                    'creator': user_url,
                    'description': topo2a.description,
                    'is_selected': True
                },
                {
                    'pk': topo2b.pk,
                    'name': topo2b.name,
                    'creator': user_url,
                    'description': topo2b.description,
                    'is_selected': True
                }
            ],
            'select_url': '/manager/surface/2/select/',
            'unselect_url': '/manager/surface/2/unselect/',
            'is_selected': True
        },
        {
            'pk': surface3.pk,
            'name': surface3.name,
            'creator': user_url,
            'description': surface3.description,
            'category': surface3.category,
            'topographies': [],
            'select_url': '/manager/surface/3/select/',
            'unselect_url': '/manager/surface/3/unselect/',
            'is_selected': True
        }
    ]

    assert ordereddict_to_dict(response.data) == expected_dicts

@pytest.mark.django_db
def test_surface_search_with_real_client(client):

    user = UserFactory()
    surface1 = SurfaceFactory(creator=user)
    surface2 = SurfaceFactory(creator=user)
    surface3 = SurfaceFactory(creator=user)

    topo1a = TopographyFactory(surface=surface1)
    topo1b = TopographyFactory(surface=surface1)
    topo2a = TopographyFactory(surface=surface2)
    topo2b = TopographyFactory(surface=surface2)

    client.force_login(user)

    #
    # select surfaces
    #

    client.post(reverse('manager:surface-select', kwargs=dict(pk=surface2.pk)))
    client.post(reverse('manager:topography-select', kwargs=dict(pk=topo1a.pk)))
    client.post(reverse('manager:surface-select', kwargs=dict(pk=surface3.pk)))

    response = client.get(reverse("manager:surface-search"))

    assert response.status_code == 200

    user_url = response.wsgi_request.build_absolute_uri(user.get_absolute_url())

    assert ordereddict_to_dict(response.data) == [
        OrderedDict([
            ("pk", surface1.pk),
            ("name", surface1.name),
            ("creator", user_url),
            ("description", surface1.description),
            ("category", surface1.category),
            ("topographies", [
                OrderedDict([
                    ("pk", topo1a.pk),
                    ("name", topo1a.name),
                    ("creator", user_url),
                    ("description", topo1a.description),
                    ("is_selected", True),
                ]),
                OrderedDict([
                    ("pk", topo1b.pk),
                    ("name", topo1b.name),
                    ("creator", user_url),
                    ("description", topo1b.description),
                    ("is_selected", False),
                ]),
            ]),
            ("select_url", reverse('manager:surface-select', kwargs=dict(pk=surface1.pk))),
            ("unselect_url", reverse('manager:surface-unselect', kwargs=dict(pk=surface1.pk))),
            ("is_selected", False)
        ]),
        OrderedDict([
            ("pk", surface2.pk),
            ("name", surface2.name),
            ("creator", user_url),
            ("description", surface2.description),
            ("category", surface2.category),
            ("topographies", [
                OrderedDict([
                    ("pk", topo2a.pk),
                    ("name", topo2a.name),
                    ("creator", user_url),
                    ("description", topo2a.description),
                    ("is_selected", True),
                ]),
                OrderedDict([
                    ("pk", topo2b.pk),
                    ("name", topo2b.name),
                    ("creator", user_url),
                    ("description", topo2b.description),
                    ("is_selected", True),
                ]),
            ]),
            ("select_url", reverse('manager:surface-select', kwargs=dict(pk=surface2.pk))),
            ("unselect_url", reverse('manager:surface-unselect', kwargs=dict(pk=surface2.pk))),
            ("is_selected", True)
        ]),
        OrderedDict([
            ("pk", surface3.pk),
            ("name", surface3.name),
            ("creator", user_url),
            ("description", surface3.description),
            ("category", surface3.category),
            ("topographies", []),
            ("select_url", reverse('manager:surface-select', kwargs=dict(pk=surface3.pk))),
            ("unselect_url", reverse('manager:surface-unselect', kwargs=dict(pk=surface3.pk))),
            ("is_selected", True)
        ])
    ]
