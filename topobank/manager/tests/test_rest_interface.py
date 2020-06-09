import pytest

from django.shortcuts import reverse
from rest_framework.test import APIRequestFactory

from ..views import select_surface, unselect_surface, SurfaceListView, SurfaceSearchPaginator,\
    select_topography, unselect_topography, \
    TagTreeView, select_tag, unselect_tag, unselect_all
from ..utils import selected_instances
from .utils import SurfaceFactory, UserFactory, TopographyFactory, TagModelFactory, ordereddicts_to_dicts

from topobank.manager.models import TagModel

@pytest.mark.django_db
def test_select_surface():
    user = UserFactory()
    surface1 = SurfaceFactory(creator=user)
    surface2 = SurfaceFactory(creator=user)
    surface3 = SurfaceFactory(creator=user)
    topo3a = TopographyFactory(surface=surface3)
    topo3b = TopographyFactory(surface=surface3)

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


@pytest.mark.django_db
def test_try_to_select_topography_but_not_allowed():
    user1 = UserFactory()
    user2 = UserFactory()
    surface1 = SurfaceFactory(creator=user1)
    topo1 = TopographyFactory(surface=surface1)

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





@pytest.mark.django_db
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
    topo1a = TopographyFactory(surface=surface1)
    topo1b = TopographyFactory(surface=surface1)
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
    request = factory.get(reverse('manager:search'))
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
            'category': None,
            'children': [
                {'creator': user_url,
                 'description': '',
                 'folder': False,
                 'key': f'topography-{topo1a.pk}',
                 'surface_key': f'surface-{surface1.pk}',
                 'name': topo1a.name,
                 'pk': topo1a.pk,
                 'selected': True,
                 'tags': [],
                 'title': topo1a.name,
                 'type': 'topography',
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
                 'selected': False,
                 'tags': [],
                 'title': topo1b.name,
                 'type': 'topography',
                 'urls': {'delete': topo1b_prefix + 'delete/',
                          'detail': topo1b_prefix,
                          'select': topo1b_prefix + 'select/',
                          'analyze': topo1b_analyze,
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
            'type': 'surface',
            'urls': {'add_topography': surface1_prefix + 'new-topography/',
                     'delete': surface1_prefix + 'delete/',
                     'detail': surface1_prefix,
                     'download': surface1_prefix + 'download/',
                     'select': surface1_prefix + 'select/',
                     'share': surface1_prefix + 'share/',
                     'analyze': surface1_analyze,
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
                 'surface_key': f'surface-{surface2.pk}',
                 'name': topo2a.name,
                 'pk': topo2a.pk,
                 'selected': False,  # not explicitly selected
                 'tags': ['bike', 'train/ice'],
                 'title': topo2a.name,
                 'type': 'topography',
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
                 'selected': False,  # not explicitly selected
                 'tags': [],
                 'title': topo2b.name,
                 'type': 'topography',
                 'urls': {'delete': topo2b_prefix + 'delete/',
                          'detail': topo2b_prefix,
                          'select': topo2b_prefix + 'select/',
                          'analyze': topo2b_analyze,
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
            'type': 'surface',
            'urls': {'add_topography': surface2_prefix + 'new-topography/',
                     'delete': surface2_prefix + 'delete/',
                     'detail': surface2_prefix,
                     'download': surface2_prefix + 'download/',
                     'select': surface2_prefix + 'select/',
                     'share': surface2_prefix + 'share/',
                     'analyze': surface2_analyze,
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
            'type': 'surface',
            'urls': {'add_topography': surface3_prefix + 'new-topography/',
                     'delete': surface3_prefix + 'delete/',
                     'detail': surface3_prefix,
                     # 'download': surface3_prefix + 'download/', # this should be missing, because no topographies yet
                     'select': surface3_prefix + 'select/',
                     'share': surface3_prefix + 'share/',
                     # 'analyze': surface3_prefix + 'show-analyses/', # this should be missing
                     'unselect': surface3_prefix + 'unselect/',
                     'update': surface3_prefix + 'update/'}
        },
    ]

    assert ordereddicts_to_dicts(response.data['page_results']) == expected_dicts

@pytest.mark.django_db
def test_tag_search_with_request_factory():
    #
    # Create some database objects
    #
    user = UserFactory()
    surface1 = SurfaceFactory(name="surface1", creator=user)
    surface2 = SurfaceFactory(name="surface2", creator=user)
    surface3 = SurfaceFactory(name="surface3", creator=user)

    topo1a = TopographyFactory(name="topo1a", surface=surface1)
    topo1b = TopographyFactory(name="topo1b", surface=surface1)
    topo2a = TopographyFactory(name="topo2a", surface=surface2)
    topo2b = TopographyFactory(name="topo2b", surface=surface2)
    # no topography for surface3 on purpose

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
        'selected': True,
        'tags': [],
        'title': topo1a.name,
        'type': 'topography',
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
        'selected': False,
        'tags': [],
        'title': topo1b.name,
        'type': 'topography',
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
        'selected': False,  # not explicitly selected
        'tags': ['bike', 'train/ice'],
        'title': topo2a.name,
        'type': 'topography',
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
        'selected': False,  # not explicitly selected
        'tags': ['train/ice/restaurant'],
        'title': topo2b.name,
        'type': 'topography',
        'urls': {'delete': topo2b_prefix + 'delete/',
                 'detail': topo2b_prefix,
                 'select': topo2b_prefix + 'select/',
                 'analyze': topo2b_analyze,
                 'unselect': topo2b_prefix + 'unselect/',
                 'update': topo2b_prefix + 'update/'}
    }

    expected_dict_surface1 = {
        'category': None,
        'children': [expected_dict_topo1a, expected_dict_topo1b],
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
        'type': 'surface',
        'urls': {'add_topography': surface1_prefix + 'new-topography/',
                 'delete': surface1_prefix + 'delete/',
                 'detail': surface1_prefix,
                 'download': surface1_prefix + 'download/',
                 'select': surface1_prefix + 'select/',
                 'share': surface1_prefix + 'share/',
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
            'pk': train_pk,
            'key': f"tag-{train_pk}",
            'folder': True,
            'name': 'train',
            'selected': False,
            'children': [
                {
                    'title': 'ice',
                    'type': 'tag',
                    'pk': train_ice_pk,
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
                            'pk': train_ice_restaurant_pk,
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
                    'pk': train_tgv_pk,
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
    assert resulted_dicts == expected_dicts


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
    topo1 = TopographyFactory(surface=surface1)

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
