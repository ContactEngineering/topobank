"""Test related to searching"""
import pytest
from unittest import TestCase

from django.shortcuts import reverse
from rest_framework.test import APIRequestFactory

from ..views import SurfaceSearchPaginator, SurfaceListView, TagTreeView
from .utils import ordereddicts_to_dicts, Topography1DFactory, UserFactory, SurfaceFactory
from ..models import TagModel


def assert_dict_equal(a, b):
    try:
        keys_a = set(a.keys())
        keys_b = set(b.keys())
    except AttributeError:
        assert a == b
        return

    assert keys_a == keys_b, f'The following keys are not present in both dictionaries: {keys_a ^ keys_b}'
    for key in keys_a:
        if isinstance(a[key], dict):
            assert_dict_equal(a[key], b[key])
        elif isinstance(a[key], list):
            assert_dicts_equal(a[key], b[key])
        else:
            assert a[key] == b[key], f'The value of the following key differs: {key}'


def assert_dicts_equal(a, b):
    for x, y in zip(a, b):
        assert_dict_equal(x, y)


@pytest.fixture
def user_three_surfaces_four_topographies():
    #
    # Create some database objects
    #
    user = UserFactory()
    surface1 = SurfaceFactory(creator=user, category='exp')
    surface2 = SurfaceFactory(creator=user, category='sim')
    surface3 = SurfaceFactory(creator=user, category='dum')

    topo1a = Topography1DFactory(surface=surface1)
    topo1b = Topography1DFactory(surface=surface1)
    topo2a = Topography1DFactory(surface=surface2)
    topo2b = Topography1DFactory(surface=surface2)
    # no topography for surface3 on purpose

    return user, surface1, surface2, surface3, topo1a, topo1b, topo2a, topo2b


@pytest.mark.django_db
def test_surface_search_with_request_factory(user_three_surfaces_four_topographies):

    user, surface1, surface2, surface3, topo1a, topo1b, topo2a, topo2b = user_three_surfaces_four_topographies

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
    request = factory.get(reverse('manager:search'))  # no search term here, see below for another search with term
    request.user = user
    request.session = session

    #
    # Create search response and compare with expectation
    #
    assert SurfaceSearchPaginator.page_size >= 3  # needed in order to get all these test results
    response = SurfaceListView.as_view()(request)

    assert response.status_code == 200

    user_url = request.build_absolute_uri(user.get_absolute_url())

    surface1_prefix = f"/manager/surface/{surface1.pk}/"
    topo1a_prefix = f"/manager/topography/{topo1a.pk}/"
    topo1b_prefix = f"/manager/topography/{topo1b.pk}/"

    surface2_prefix = f"/manager/surface/{surface2.pk}/"
    topo2a_prefix = f"/manager/topography/{topo2a.pk}/"
    topo2b_prefix = f"/manager/topography/{topo2b.pk}/"

    surface3_prefix = f"/manager/surface/{surface3.pk}/"

    topo1a_analyze = f"/analysis/topography/{topo1a.pk}/"
    topo1b_analyze = f"/analysis/topography/{topo1b.pk}/"
    topo2a_analyze = f"/analysis/topography/{topo2a.pk}/"
    topo2b_analyze = f"/analysis/topography/{topo2b.pk}/"
    surface1_analyze = f"/analysis/surface/{surface1.pk}/"
    surface2_analyze = f"/analysis/surface/{surface2.pk}/"

    expected_dicts = [
        {
            'category': 'exp',
            'category_name': 'Experimental data',
            'children': [
                {'creator': user_url,
                 'description': '',
                 'folder': False,
                 'key': f'topography-{topo1a.pk}',
                 'surface_key': f'surface-{surface1.pk}',
                 'name': topo1a.name,
                 'pk': topo1a.pk,
                 'publication_authors': '',
                 'publication_date': '',
                 'selected': True,
                 'tags': [],
                 'title': topo1a.name,
                 'type': 'topography',
                 'version': '',
                 'urls': {'delete': topo1a_prefix + 'delete/',
                          'detail': topo1a_prefix,
                          'select': topo1a_prefix + 'select/',
                          'analyze': topo1a_analyze,
                          'unselect': topo1a_prefix + 'unselect/',
                          'update': topo1a_prefix + 'update/'}},
                {'creator': user_url,
                 'description': '',
                 'folder': False,
                 'key': f'topography-{topo1b.pk}',
                 'surface_key': f'surface-{surface1.pk}',
                 'name': topo1b.name,
                 'pk': topo1b.pk,
                 'publication_authors': '',
                 'publication_date': '',
                 'selected': False,
                 'tags': [],
                 'title': topo1b.name,
                 'type': 'topography',
                 'version': '',
                 'urls': {'delete': topo1b_prefix + 'delete/',
                          'detail': topo1b_prefix,
                          'select': topo1b_prefix + 'select/',
                          'analyze': topo1b_analyze,
                          'unselect': topo1b_prefix + 'unselect/',
                          'update': topo1b_prefix + 'update/'}},

            ],
            'creator': user_url,
            'creator_name': user.name,
            'description': '',
            'folder': True,
            'key': f'surface-{surface1.pk}',
            'name': surface1.name,
            'pk': surface1.pk,
            'publication_authors': '',
            'publication_date': '',
            'publication_license': '',
            'selected': False,
            'sharing_status': 'own',
            'tags': ['bike', 'train/tgv'],
            'title': surface1.name,
            'topography_count': 2,
            'type': 'surface',
            'version': '',
            'urls': {'add_topography': surface1_prefix + 'new-topography/',
                     'delete': surface1_prefix + 'delete/',
                     'detail': surface1_prefix,
                     'download': surface1_prefix + 'download/',
                     'select': surface1_prefix + 'select/',
                     'share': surface1_prefix + 'share/',
                     'publish': surface1_prefix + 'publish/',
                     'analyze': surface1_analyze,
                     'unselect': surface1_prefix + 'unselect/',
                     'update': surface1_prefix + 'update/'}
        },
        {
            'category': 'sim',
            'category_name': 'Simulated data',
            'children': [
                {'creator': user_url,
                 'description': '',
                 'folder': False,
                 'key': f'topography-{topo2a.pk}',
                 'surface_key': f'surface-{surface2.pk}',
                 'name': topo2a.name,
                 'pk': topo2a.pk,
                 'publication_authors': '',
                 'publication_date': '',
                 'selected': False,  # not explicitly selected
                 'tags': ['bike', 'train/ice'],
                 'title': topo2a.name,
                 'type': 'topography',
                 'version': '',
                 'urls': {'delete': topo2a_prefix + 'delete/',
                          'detail': topo2a_prefix,
                          'select': topo2a_prefix + 'select/',
                          'analyze': topo2a_analyze,
                          'unselect': topo2a_prefix + 'unselect/',
                          'update': topo2a_prefix + 'update/'}},
                {'creator': user_url,
                 'description': '',
                 'folder': False,
                 'key': f'topography-{topo2b.pk}',
                 'surface_key': f'surface-{surface2.pk}',
                 'name': topo2b.name,
                 'pk': topo2b.pk,
                 'publication_authors': '',
                 'publication_date': '',
                 'selected': False,  # not explicitly selected
                 'tags': [],
                 'title': topo2b.name,
                 'type': 'topography',
                 'version': '',
                 'urls': {'delete': topo2b_prefix + 'delete/',
                          'detail': topo2b_prefix,
                          'select': topo2b_prefix + 'select/',
                          'analyze': topo2b_analyze,
                          'unselect': topo2b_prefix + 'unselect/',
                          'update': topo2b_prefix + 'update/'}},

            ],
            'creator': user_url,
            'creator_name': user.name,
            'description': '',
            'folder': True,
            'key': f'surface-{surface2.pk}',
            'name': surface2.name,
            'pk': surface2.pk,
            'publication_authors': '',
            'publication_date': '',
            'publication_license': '',
            'selected': True,
            'sharing_status': 'own',
            'tags': [],
            'title': surface2.name,
            'topography_count': 2,
            'type': 'surface',
            'version': '',
            'urls': {'add_topography': surface2_prefix + 'new-topography/',
                     'delete': surface2_prefix + 'delete/',
                     'detail': surface2_prefix,
                     'download': surface2_prefix + 'download/',
                     'select': surface2_prefix + 'select/',
                     'share': surface2_prefix + 'share/',
                     'publish': surface2_prefix + 'publish/',
                     'analyze': surface2_analyze,
                     'unselect': surface2_prefix + 'unselect/',
                     'update': surface2_prefix + 'update/'}
        },
        {
            'category': 'dum',
            'category_name': 'Dummy data',
            'children': [],
            'creator': user_url,
            'creator_name': user.name,
            'description': '',
            'folder': True,
            'key': f'surface-{surface3.pk}',
            'name': surface3.name,
            'pk': surface3.pk,
            'publication_authors': '',
            'publication_date': '',
            'publication_license': '',
            'selected': True,
            'sharing_status': 'own',
            'tags': [],
            'title': surface3.name,
            'topography_count': 0,
            'type': 'surface',
            'version': '',
            'urls': {'add_topography': surface3_prefix + 'new-topography/',
                     'delete': surface3_prefix + 'delete/',
                     'detail': surface3_prefix,
                     'download': surface3_prefix + 'download/',
                     'select': surface3_prefix + 'select/',
                     'share': surface3_prefix + 'share/',
                     'publish': surface3_prefix + 'publish/',
                     # 'analyze': surface3_prefix + 'show-analyses/', # this should be missing
                     'unselect': surface3_prefix + 'unselect/',
                     'update': surface3_prefix + 'update/'}
        },
    ]

    assert_dicts_equal(ordereddicts_to_dicts(response.data['page_results']), expected_dicts)

    #
    # Do a search and check for reduced results because search for "topo2a"
    #
    request = factory.get(reverse('manager:search')+f"?search={topo2a.name}")
    request.user = user
    request.session = session

    #
    # Create search response and compare with expectation
    #
    response = SurfaceListView.as_view()(request)

    assert response.status_code == 200

    expected_dicts = [
        {
            'category': 'sim',
            'category_name': 'Simulated data',
            'children': [
                {'creator': user_url,
                 'description': '',
                 'folder': False,
                 'key': f'topography-{topo2a.pk}',
                 'surface_key': f'surface-{surface2.pk}',
                 'name': topo2a.name,
                 'pk': topo2a.pk,
                 'publication_authors': '',
                 'publication_date': '',
                 'selected': False,  # not explicitly selected
                 'tags': ['bike', 'train/ice'],
                 'title': topo2a.name,
                 'type': 'topography',
                 'version': '',
                 'urls': {'delete': topo2a_prefix + 'delete/',
                          'detail': topo2a_prefix,
                          'select': topo2a_prefix + 'select/',
                          'analyze': topo2a_analyze,
                          'unselect': topo2a_prefix + 'unselect/',
                          'update': topo2a_prefix + 'update/'}},
            ],
            'creator': user_url,
            'creator_name': user.name,
            'description': '',
            'folder': True,
            'key': f'surface-{surface2.pk}',
            'name': surface2.name,
            'pk': surface2.pk,
            'publication_authors': '',
            'publication_date': '',
            'publication_license': '',
            'selected': True,
            'sharing_status': 'own',
            'tags': [],
            'title': surface2.name,
            'topography_count': 2,
            'type': 'surface',
            'version': '',
            'urls': {'add_topography': surface2_prefix + 'new-topography/',
                     'delete': surface2_prefix + 'delete/',
                     'detail': surface2_prefix,
                     'download': surface2_prefix + 'download/',
                     'select': surface2_prefix + 'select/',
                     'share': surface2_prefix + 'share/',
                     'publish': surface2_prefix + 'publish/',
                     'analyze': surface2_analyze,
                     'unselect': surface2_prefix + 'unselect/',
                     'update': surface2_prefix + 'update/'}
        },
    ]

    resulted_dicts = ordereddicts_to_dicts(response.data['page_results'], sorted_by='title')
    assert_dicts_equal(resulted_dicts, expected_dicts)

    #
    # Do a search and check for reduced results because search for category "exp"
    #
    request = factory.get(reverse('manager:search') + "?category=exp")
    request.user = user
    request.session = session

    #
    # Create search response and compare with expectation
    #
    response = SurfaceListView.as_view()(request)

    assert response.status_code == 200

    expected_dicts = [
        {
            'category': 'exp',
            'category_name': 'Experimental data',
            'children': [
                {'creator': user_url,
                 'description': '',
                 'folder': False,
                 'key': f'topography-{topo1a.pk}',
                 'surface_key': f'surface-{surface1.pk}',
                 'name': topo1a.name,
                 'pk': topo1a.pk,
                 'publication_authors': '',
                 'publication_date': '',
                 'selected': True,
                 'tags': [],
                 'title': topo1a.name,
                 'type': 'topography',
                 'version': '',
                 'urls': {'delete': topo1a_prefix + 'delete/',
                          'detail': topo1a_prefix,
                          'select': topo1a_prefix + 'select/',
                          'analyze': topo1a_analyze,
                          'unselect': topo1a_prefix + 'unselect/',
                          'update': topo1a_prefix + 'update/'}},
                {'creator': user_url,
                 'description': '',
                 'folder': False,
                 'key': f'topography-{topo1b.pk}',
                 'surface_key': f'surface-{surface1.pk}',
                 'name': topo1b.name,
                 'pk': topo1b.pk,
                 'publication_authors': '',
                 'publication_date': '',
                 'selected': False,
                 'tags': [],
                 'title': topo1b.name,
                 'type': 'topography',
                 'version': '',
                 'urls': {'delete': topo1b_prefix + 'delete/',
                          'detail': topo1b_prefix,
                          'select': topo1b_prefix + 'select/',
                          'analyze': topo1b_analyze,
                          'unselect': topo1b_prefix + 'unselect/',
                          'update': topo1b_prefix + 'update/'}},

            ],
            'creator': user_url,
            'creator_name': user.name,
            'description': '',
            'folder': True,
            'key': f'surface-{surface1.pk}',
            'name': surface1.name,
            'pk': surface1.pk,
            'publication_authors': '',
            'publication_date': '',
            'publication_license': '',
            'selected': False,
            'sharing_status': 'own',
            'tags': ['bike', 'train/tgv'],
            'title': surface1.name,
            'topography_count': 2,
            'type': 'surface',
            'version': '',
            'urls': {'add_topography': surface1_prefix + 'new-topography/',
                     'delete': surface1_prefix + 'delete/',
                     'detail': surface1_prefix,
                     'download': surface1_prefix + 'download/',
                     'select': surface1_prefix + 'select/',
                     'share': surface1_prefix + 'share/',
                     'publish': surface1_prefix + 'publish/',
                     'analyze': surface1_analyze,
                     'unselect': surface1_prefix + 'unselect/',
                     'update': surface1_prefix + 'update/'}
        },
    ]

    resulted_dicts = ordereddicts_to_dicts(response.data['page_results'], sorted_by='title')
    assert_dicts_equal(resulted_dicts, expected_dicts)


@pytest.mark.django_db
def test_tag_search_with_request_factory(user_three_surfaces_four_topographies):
    user, surface1, surface2, surface3, topo1a, topo1b, topo2a, topo2b = user_three_surfaces_four_topographies

    #
    # Set some tags
    #
    surface1.tags = ['bike', 'train/tgv']
    surface1.save()
    topo2a.tags = ['bike', 'train/ice']
    topo2a.save()
    topo2b.tags = ['train/ice/restaurant']
    topo2b.save()

    #
    # Fix a selection and create a request with this selection
    #
    session = dict(selection=[f'surface-{surface2.pk}', f'topography-{topo1a.pk}', f'surface-{surface3.pk}'])

    factory = APIRequestFactory()
    request = factory.get(reverse('manager:tag-list'))
    request.user = user
    request.session = session

    #
    # Create tag tree and compare with expectation
    #
    response = TagTreeView.as_view()(request)

    assert response.status_code == 200

    user_url = request.build_absolute_uri(user.get_absolute_url())

    surface1_prefix = f"/manager/surface/{surface1.pk}/"
    topo1a_prefix = f"/manager/topography/{topo1a.pk}/"
    topo1b_prefix = f"/manager/topography/{topo1b.pk}/"

    surface2_prefix = f"/manager/surface/{surface2.pk}/"
    topo2a_prefix = f"/manager/topography/{topo2a.pk}/"
    topo2b_prefix = f"/manager/topography/{topo2b.pk}/"

    surface3_prefix = f"/manager/surface/{surface3.pk}/"

    topo1a_analyze = f"/analysis/topography/{topo1a.pk}/"
    topo1b_analyze = f"/analysis/topography/{topo1b.pk}/"
    topo2a_analyze = f"/analysis/topography/{topo2a.pk}/"
    topo2b_analyze = f"/analysis/topography/{topo2b.pk}/"
    surface1_analyze = f"/analysis/surface/{surface1.pk}/"
    surface2_analyze = f"/analysis/surface/{surface2.pk}/"

    expected_dict_topo1a = {
        'creator': user_url,
        'description': '',
        'folder': False,
        'key': f'topography-{topo1a.pk}',
        'surface_key': f'surface-{surface1.pk}',
        'name': topo1a.name,
        'pk': topo1a.pk,
        'publication_authors': '',
        'publication_date': '',
        'selected': True,
        'tags': [],
        'title': topo1a.name,
        'type': 'topography',
        'version': '',
        'urls': {'delete': topo1a_prefix + 'delete/',
                 'detail': topo1a_prefix,
                 'select': topo1a_prefix + 'select/',
                 'analyze': topo1a_analyze,
                 'unselect': topo1a_prefix + 'unselect/',
                 'update': topo1a_prefix + 'update/'}
    }
    expected_dict_topo1b = {
        'creator': user_url,
        'description': '',
        'folder': False,
        'key': f'topography-{topo1b.pk}',
        'surface_key': f'surface-{surface1.pk}',
        'name': topo1b.name,
        'pk': topo1b.pk,
        'publication_authors': '',
        'publication_date': '',
        'selected': False,
        'tags': [],
        'title': topo1b.name,
        'type': 'topography',
        'version': '',
        'urls': {'delete': topo1b_prefix + 'delete/',
                 'detail': topo1b_prefix,
                 'select': topo1b_prefix + 'select/',
                 'analyze': topo1b_analyze,
                 'unselect': topo1b_prefix + 'unselect/',
                 'update': topo1b_prefix + 'update/'}
    }

    expected_dict_topo2a = {
        'creator': user_url,
        'description': '',
        'folder': False,
        'key': f'topography-{topo2a.pk}',
        'surface_key': f'surface-{surface2.pk}',
        'name': topo2a.name,
        'pk': topo2a.pk,
        'publication_authors': '',
        'publication_date': '',
        'selected': False,  # not explicitly selected
        'tags': ['bike', 'train/ice'],
        'title': topo2a.name,
        'type': 'topography',
        'version': '',
        'urls': {'delete': topo2a_prefix + 'delete/',
                 'detail': topo2a_prefix,
                 'select': topo2a_prefix + 'select/',
                 'analyze': topo2a_analyze,
                 'unselect': topo2a_prefix + 'unselect/',
                 'update': topo2a_prefix + 'update/'}
    }

    expected_dict_topo2b = {
        'creator': user_url,
        'description': '',
        'folder': False,
        'key': f'topography-{topo2b.pk}',
        'surface_key': f'surface-{surface2.pk}',
        'name': topo2b.name,
        'pk': topo2b.pk,
        'publication_authors': '',
        'publication_date': '',
        'selected': False,  # not explicitly selected
        'tags': ['train/ice/restaurant'],
        'title': topo2b.name,
        'type': 'topography',
        'version': '',
        'urls': {'delete': topo2b_prefix + 'delete/',
                 'detail': topo2b_prefix,
                 'select': topo2b_prefix + 'select/',
                 'analyze': topo2b_analyze,
                 'unselect': topo2b_prefix + 'unselect/',
                 'update': topo2b_prefix + 'update/'}
    }

    expected_dict_surface1 = {
        'category': 'exp',
        'category_name': 'Experimental data',
        'children': [expected_dict_topo1a, expected_dict_topo1b],
        'creator': user_url,
        'creator_name': user.name,
        'description': '',
        'folder': True,
        'key': f'surface-{surface1.pk}',
        'name': surface1.name,
        'pk': surface1.pk,
        'publication_authors': '',
        'publication_date': '',
        'publication_license': '',
        'selected': False,
        'sharing_status': 'own',
        'tags': ['bike', 'train/tgv'],
        'title': surface1.name,
        'topography_count': 2,
        'type': 'surface',
        'version': '',
        'urls': {'add_topography': surface1_prefix + 'new-topography/',
                 'delete': surface1_prefix + 'delete/',
                 'detail': surface1_prefix,
                 'download': surface1_prefix + 'download/',
                 'select': surface1_prefix + 'select/',
                 'share': surface1_prefix + 'share/',
                 'publish': surface1_prefix + 'publish/',
                 'analyze': surface1_analyze,
                 'unselect': surface1_prefix + 'unselect/',
                 'update': surface1_prefix + 'update/'}
    }

    bike_pk = TagModel.objects.get(name='bike').pk
    train_pk = TagModel.objects.get(name='train').pk
    train_ice_pk = TagModel.objects.get(name='train/ice').pk
    train_tgv_pk = TagModel.objects.get(name='train/tgv').pk
    train_ice_restaurant_pk = TagModel.objects.get(name='train/ice/restaurant').pk

    bike_prefix = f"/manager/tag/{bike_pk}/"
    train_prefix = f"/manager/tag/{train_pk}/"
    train_ice_prefix = f"/manager/tag/{train_ice_pk}/"
    train_tgv_prefix = f"/manager/tag/{train_tgv_pk}/"
    train_ice_restaurant_prefix = f"/manager/tag/{train_ice_restaurant_pk}/"

    expected_dicts = [
        {
            'title': 'bike',
            'type': 'tag',
            'version': '',
            'publication_authors': '',
            'publication_date': '',
            'pk': bike_pk,
            'key': f'tag-{bike_pk}',
            'folder': True,
            'name': 'bike',
            'selected': False,
            'children': [
                # surface1, topo2a
                expected_dict_topo2a,
                expected_dict_surface1,
            ],
            'urls': {
                'select': bike_prefix + 'select/',
                'unselect': bike_prefix + 'unselect/'
            }
        },
        {
            'title': 'train',
            'type': 'tag',
            'version': '',
            'publication_authors': '',
            'publication_date': '',
            'pk': train_pk,
            'key': f"tag-{train_pk}",
            'folder': True,
            'name': 'train',
            'selected': False,
            'children': [
                {
                    'title': 'ice',
                    'type': 'tag',
                    'version': '',
                    'pk': train_ice_pk,
                    'publication_authors': '',
                    'publication_date': '',
                    'key': f"tag-{train_ice_pk}",
                    'folder': True,
                    'name': 'train/ice',
                    'selected': False,
                    'children': [
                        # topo2a
                        expected_dict_topo2a,
                        {
                            'title': 'restaurant',
                            'type': 'tag',
                            'version': '',
                            'pk': train_ice_restaurant_pk,
                            'publication_authors': '',
                            'publication_date': '',
                            'key': f"tag-{train_ice_restaurant_pk}",
                            'folder': True,
                            'name': 'train/ice/restaurant',
                            'selected': False,
                            'children': [
                                # topo2b
                                expected_dict_topo2b
                            ],
                            'urls': {
                                'select': train_ice_restaurant_prefix + 'select/',
                                'unselect': train_ice_restaurant_prefix + 'unselect/'
                            }
                        }
                    ],
                    'urls': {
                        'select': train_ice_prefix+'select/',
                        'unselect': train_ice_prefix+'unselect/'
                    }
                },
                {
                    'title': 'tgv',
                    'type': 'tag',
                    'version': '',
                    'pk': train_tgv_pk,
                    'publication_authors': '',
                    'publication_date': '',
                    'key': f"tag-{train_tgv_pk}",
                    'folder': True,
                    'name': 'train/tgv',
                    'selected': False,
                    'children': [
                        # surface1
                        expected_dict_surface1
                    ],
                    'urls': {
                        'select': train_tgv_prefix + 'select/',
                        'unselect': train_tgv_prefix + 'unselect/'
                    }
                }
            ],
            'urls': {
                'select': train_prefix + 'select/',
                'unselect': train_prefix + 'unselect/'
            }
        },

    ]

    resulted_dicts = ordereddicts_to_dicts(response.data['page_results'], sorted_by='title')
    assert_dicts_equal(resulted_dicts, expected_dicts)

    #
    # Now restrict result by query parameters, search for "topo2a"
    #
    request = factory.get(reverse('manager:tag-list')+f"?search={topo2a.name}")
    request.user = user
    request.session = session

    #
    # Create tag tree and compare with expectation
    #
    response = TagTreeView.as_view()(request)

    assert response.status_code == 200

    # only tags "bike" and "train/ice" should be included
    # all other tags should be missing
    expected_dicts = [
        {
            'title': 'bike',
            'type': 'tag',
            'version': '',
            'pk': bike_pk,
            'publication_authors': '',
            'publication_date': '',
            'key': f'tag-{bike_pk}',
            'folder': True,
            'name': 'bike',
            'selected': False,
            'children': [
                # only topo2a is matching
                expected_dict_topo2a,
            ],
            'urls': {
                'select': bike_prefix + 'select/',
                'unselect': bike_prefix + 'unselect/'
            }
        },
        {
            'title': 'train',
            'type': 'tag',
            'version': '',
            'pk': train_pk,
            'publication_authors': '',
            'publication_date': '',
            'key': f"tag-{train_pk}",
            'folder': True,
            'name': 'train',
            'selected': False,
            'children': [
                {
                    'title': 'ice',
                    'type': 'tag',
                    'version': '',
                    'pk': train_ice_pk,
                    'publication_authors': '',
                    'publication_date': '',
                    'key': f"tag-{train_ice_pk}",
                    'folder': True,
                    'name': 'train/ice',
                    'selected': False,
                    'children': [
                        # topo2a
                        expected_dict_topo2a
                    ],
                    'urls': {
                        'select': train_ice_prefix + 'select/',
                        'unselect': train_ice_prefix + 'unselect/'
                    }
                },

            ],
            'urls': {
                'select': train_prefix + 'select/',
                'unselect': train_prefix + 'unselect/'
            }
        },

    ]
    resulted_dicts = ordereddicts_to_dicts(response.data['page_results'], sorted_by='title')
    assert_dicts_equal(resulted_dicts, expected_dicts)

    #
    # Now restrict result by query parameters, search for category 'dum'
    # -> no result, because surface 3 would match, but has no tag
    #
    request = factory.get(reverse('manager:tag-list')+"?category=dum")
    request.user = user
    request.session = session

    #
    # Create tag tree and compare with expectation
    #
    response = TagTreeView.as_view()(request)

    assert response.status_code == 200

    # no results expected
    resulted_dicts = ordereddicts_to_dicts(response.data['page_results'], sorted_by='title')
    assert resulted_dicts == []

    #
    # Now create another surface and share with this active user, than filter only for shared
    #
    user2 = UserFactory()
    surface4 = SurfaceFactory(creator=user2)
    surface4.tags = ['shared']
    surface4.save()
    surface4.share(user)

    shared_pk = TagModel.objects.get(name='shared').pk
    shared_prefix = f"/manager/tag/{shared_pk}/"
    surface4_prefix = f"/manager/surface/{surface4.pk}/"

    request = factory.get(reverse('manager:tag-list') + "?sharing_status=shared")
    request.user = user
    request.session = session

    #
    # Create tag tree and compare with expectation
    #
    response = TagTreeView.as_view()(request)

    assert response.status_code == 200

    expected_dicts = [
        {
            'title': 'shared',
            'type': 'tag',
            'version': '',
            'pk': shared_pk,
            'publication_authors': '',
            'publication_date': '',
            'key': f"tag-{shared_pk}",
            'folder': True,
            'name': 'shared',
            'selected': False,
            'children': [
                {
                    'title': surface4.name,
                    'type': 'surface',
                    'version': '',
                    'pk': surface4.pk,
                    'publication_authors': '',
                    'publication_date': '',
                    'key': f"surface-{surface4.pk}",
                    'folder': False,
                    'name': surface4.name,
                    'selected': False,
                    'children': [],
                    'urls': {
                        'select': surface4_prefix + 'select/',
                        'unselect': surface4_prefix + 'unselect/'
                    }
                },
            ],
            'urls': {
                'select': shared_prefix + 'select/',
                'unselect': shared_prefix + 'unselect/'
            }
        },
    ]


@pytest.mark.django_db
def test_search_expressions_with_request_factory():

    user = UserFactory()

    surface1 = SurfaceFactory(creator=user)

    topo1a = Topography1DFactory(surface=surface1, description="a big tiger")
    topo1b = Topography1DFactory(surface=surface1, description="a big elephant")
    topo1c = Topography1DFactory(surface=surface1, description="Find this here and a small ant")
    topo1d = Topography1DFactory(surface=surface1, description="not me, big snake")

    surface2 = SurfaceFactory(creator=user)

    topo2a = Topography1DFactory(surface=surface2, name='Measurement 2A')
    topo2b = Topography1DFactory(surface=surface2, name='Measurement 2B', description="a small lion")

    #
    # Set some tags
    #
    topo1b.tags = ['bike']
    topo1b.save()
    topo1c.tags = ['transport/bike']
    topo1c.save()
    topo1d.tags = ['bike']
    topo1d.save()

    #
    # Define helper function for testing searching
    #
    factory = APIRequestFactory()

    def search_surfaces(expr):
        """Search given given expression and return dicts with results"""
        request = factory.get(reverse('manager:search')+f"?search={expr}")
        request.user = user
        request.session = {}  # must be there
        response = SurfaceListView.as_view()(request)
        assert response.status_code == 200
        return ordereddicts_to_dicts(response.data['page_results'], sorted_by='title')

    # simple search for a topography by name given a phrase
    result = search_surfaces(f"'{topo2a.name}'")
    assert len(result) == 1  # one surface
    assert len(result[0]['children']) == 1  # one topography
    assert result[0]['children'][0]['name'] == topo2a.name

    # AND search for topographies by name
    result = search_surfaces(f'"{topo2a.name}" "{topo1a.name}"')
    assert len(result) == 0  # no surfaces

    # OR search for topographies by name
    result = search_surfaces(f'"{topo2a.name}" OR "{topo1a.name}"')
    assert len(result) == 2  # two surfaces
    # noinspection DuplicatedCode
    assert len(result[0]['children']) == 1  # one topography
    assert len(result[1]['children']) == 1  # one topography
    assert result[0]['children'][0]['name'] == topo1a.name
    assert result[1]['children'][0]['name'] == topo2a.name

    # Exclusion using '-'
    result = search_surfaces(f'-elephant')
    assert len(result) == 2
    assert result[0]['name'] == surface1.name
    assert result[1]['name'] == surface2.name
    assert len(result[0]['children']) == 3  # here one measurement is excluded
    assert len(result[1]['children']) == 2

    # Searching nearby
    result = search_surfaces(f'Find * here')
    assert len(result) == 1
    assert result[0]['name'] == surface1.name
    assert len(result[0]['children']) == 1  # here one measurement has it
    assert result[0]['children'][0]["description"] == "Find this here and a small ant"

    # more complex search expression using a phrase
    #
    # Parentheses do not work with 'websearch' for simplicity.
    #
    # (NOT) binds most tightly, "quoted text" (FOLLOWED BY) next most tightly,
    # then AND (default if no parameter), with OR binding the least tightly.
    #

    # result = search_surfaces(f'bike AND "a big" or "a small" -"not me"')
    result = search_surfaces(f'bike -snake big')

    assert len(result) == 1  # surface 2 is excluded because there is no "bike"
    assert result[0]['name'] == surface1.name
    assert len(result[0]['children']) == 1
    assert result[0]['children'][0]["name"] == topo1b.name  # topo1d is excluded because of 'not me'




