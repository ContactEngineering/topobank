import json

import pytest

from django.shortcuts import reverse

from guardian.shortcuts import get_anonymous_user

from ...manager.utils import subjects_to_base64
from ...manager.models import Surface, Topography
from .utils import two_topos, two_users


@pytest.mark.django_db
@pytest.mark.parametrize('is_authenticated', [True, False])
def test_surface_retrieve_routes(api_client, is_authenticated, two_topos, handle_usage_statistics):
    topo1, topo2 = two_topos
    user = topo1.creator
    assert topo2.creator == user

    surface1 = topo1.surface
    surface2 = topo2.surface

    anonymous_user = get_anonymous_user()
    assert not anonymous_user.has_perm('view_surface', surface1)
    assert not anonymous_user.has_perm('view_surface', surface2)
    assert user.has_perm('view_surface', surface1)
    assert user.has_perm('view_surface', surface2)

    surface1_dict = {'category': None,
                     'category_name': None,
                     'children': [{'creator': 'http://testserver/users/testuser/',
                                   'creator_name': topo1.creator.name,
                                   'description': 'description1',
                                   'folder': False,
                                   'id': topo1.id,
                                   'key': f'topography-{topo1.id}',
                                   'label': 'Example 3 - ZSensor',
                                   'name': 'Example 3 - ZSensor',
                                   'publication_authors': '',
                                   'publication_date': '',
                                   'selected': False,
                                   'sharing_status': 'own',
                                   'surface_key': f'surface-{surface1.id}',
                                   'tags': [],
                                   'title': 'Example 3 - ZSensor',
                                   'type': 'topography',
                                   'urls': {'analyze': f'/analysis/html/list/?subjects={subjects_to_base64([topo1])}',
                                            'delete': f'/manager/html/topography/{topo1.id}/delete/',
                                            'detail': f'/manager/html/topography/{topo1.id}/',
                                            'select': f'/manager/api/selection/topography/{topo1.id}/select/',
                                            'unselect': f'/manager/api/selection/topography/{topo1.id}/unselect/',
                                            'update': f'/manager/html/topography/{topo1.id}/update/'},
                                   'version': ''}],
                     'creator': 'http://testserver/users/testuser/',
                     'creator_name': surface1.creator.name,
                     'description': '',
                     'folder': True,
                     'id': surface1.id,
                     'key': f'surface-{surface1.id}',
                     'label': 'Surface 1',
                     'name': 'Surface 1',
                     'publication_authors': '',
                     'publication_date': '',
                     'publication_license': '',
                     'selected': False,
                     'sharing_status': 'own',
                     'tags': [],
                     'title': 'Surface 1',
                     'topography_count': 1,
                     'type': 'surface',
                     'urls': {'add_topography': f'/manager/html/surface/{surface1.id}/new-topography/',
                              'analyze': f'/analysis/html/list/?subjects={subjects_to_base64([surface1])}',
                              'delete': f'/manager/html/surface/{surface1.id}/delete/',
                              'detail': f'/manager/html/surface/{surface1.id}/',
                              'download': f'/manager/surface/{surface1.id}/download/',
                              'publish': f'/manager/html/surface/{surface1.id}/publish/',
                              'select': f'/manager/api/selection/surface/{surface1.id}/select/',
                              'share': f'/manager/html/surface/{surface1.id}/share/',
                              'unselect': f'/manager/api/selection/surface/{surface1.id}/unselect/',
                              'update': f'/manager/html/surface/{surface1.id}/update/'},
                     'version': ''}
    surface2_dict = {'category': None,
                     'category_name': None,
                     'children': [{'creator': 'http://testserver/users/testuser/',
                                   'creator_name': topo2.creator.name,
                                   'description': 'description2',
                                   'folder': False,
                                   'id': topo2.id,
                                   'key': f'topography-{topo2.id}',
                                   'label': 'Example 4 - Default',
                                   'name': 'Example 4 - Default',
                                   'publication_authors': '',
                                   'publication_date': '',
                                   'selected': False,
                                   'sharing_status': 'own',
                                   'surface_key': f'surface-{surface2.id}',
                                   'tags': [],
                                   'title': 'Example 4 - Default',
                                   'type': 'topography',
                                   'urls': {'analyze': f'/analysis/html/list/?subjects={subjects_to_base64([topo2])}',
                                            'delete': f'/manager/html/topography/{topo2.id}/delete/',
                                            'detail': f'/manager/html/topography/{topo2.id}/',
                                            'select': f'/manager/api/selection/topography/{topo2.id}/select/',
                                            'unselect': f'/manager/api/selection/topography/{topo2.id}/unselect/',
                                            'update': f'/manager/html/topography/{topo2.id}/update/'},
                                   'version': ''}],
                     'creator': 'http://testserver/users/testuser/',
                     'creator_name': surface2.creator.name,
                     'description': '',
                     'folder': True,
                     'id': surface2.id,
                     'key': f'surface-{surface2.id}',
                     'label': 'Surface 2',
                     'name': 'Surface 2',
                     'publication_authors': '',
                     'publication_date': '',
                     'publication_license': '',
                     'selected': False,
                     'sharing_status': 'own',
                     'tags': [],
                     'title': 'Surface 2',
                     'topography_count': 1,
                     'type': 'surface',
                     'urls': {'add_topography': f'/manager/html/surface/{surface2.id}/new-topography/',
                              'analyze': f'/analysis/html/list/?subjects={subjects_to_base64([surface2])}',
                              'delete': f'/manager/html/surface/{surface2.id}/delete/',
                              'detail': f'/manager/html/surface/{surface2.id}/',
                              'download': f'/manager/surface/{surface2.id}/download/',
                              'publish': f'/manager/html/surface/{surface2.id}/publish/',
                              'select': f'/manager/api/selection/surface/{surface2.id}/select/',
                              'share': f'/manager/html/surface/{surface2.id}/share/',
                              'unselect': f'/manager/api/selection/surface/{surface2.id}/unselect/',
                              'update': f'/manager/html/surface/{surface2.id}/update/'},
                     'version': ''}

    if is_authenticated:
        api_client.force_authenticate(user)

    response = api_client.get(reverse('manager:surface-api-list'))
    assert response.status_code == 405

    response = api_client.get(reverse('manager:surface-api-detail', kwargs=dict(pk=surface1.id)))
    if is_authenticated:
        assert response.status_code == 200
        data = json.loads(json.dumps(response.data))  # Convert OrderedDict to dict
        assert data == surface1_dict
    else:
        # Anonymous user does not have access by default
        assert response.status_code == 404

    response = api_client.get(reverse('manager:surface-api-detail', kwargs=dict(pk=surface2.id)))
    if is_authenticated:
        assert response.status_code == 200
        data = json.loads(json.dumps(response.data))  # Convert OrderedDict to dict
        assert data == surface2_dict
    else:
        # Anonymous user does not have access by default
        assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize('is_authenticated', [True, False])
def test_topography_retrieve_routes(api_client, is_authenticated, two_topos, handle_usage_statistics):
    topo1, topo2 = two_topos
    user = topo1.creator
    assert topo2.creator == user

    anonymous_user = get_anonymous_user()
    assert not anonymous_user.has_perm('view_surface', topo1.surface)
    assert user.has_perm('view_surface', topo1.surface)

    topo1_dict = {'id': topo1.id,
                  'type': 'topography',
                  'name': 'Example 3 - ZSensor',
                  'creator': 'http://testserver/users/testuser/',
                  'description': 'description1',
                  'tags': [],
                  'urls': {'analyze': f'/analysis/html/list/?subjects={subjects_to_base64([topo1])}',
                           'delete': f'/manager/html/topography/{topo1.id}/delete/',
                           'detail': f'/manager/html/topography/{topo1.id}/',
                           'select': f'/manager/api/selection/topography/{topo1.id}/select/',
                           'unselect': f'/manager/api/selection/topography/{topo1.id}/unselect/',
                           'update': f'/manager/html/topography/{topo1.id}/update/'},
                  'selected': False,
                  'key': f'topography-{topo1.id}',
                  'surface_key': f'surface-{topo1.surface.id}',
                  'title': 'Example 3 - ZSensor',
                  'folder': False,
                  'version': '',
                  'publication_date': '',
                  'publication_authors': '',
                  'creator_name': topo1.creator.name,
                  'sharing_status': 'own',
                  'label': 'Example 3 - ZSensor'}
    topo2_dict = {'id': topo2.id,
                  'type': 'topography',
                  'name': 'Example 4 - Default',
                  'creator': 'http://testserver/users/testuser/',
                  'description': 'description2',
                  'tags': [],
                  'urls': {'analyze': f'/analysis/html/list/?subjects={subjects_to_base64([topo2])}',
                           'delete': f'/manager/html/topography/{topo2.id}/delete/',
                           'detail': f'/manager/html/topography/{topo2.id}/',
                           'select': f'/manager/api/selection/topography/{topo2.id}/select/',
                           'unselect': f'/manager/api/selection/topography/{topo2.id}/unselect/',
                           'update': f'/manager/html/topography/{topo2.id}/update/'},
                  'selected': False,
                  'key': f'topography-{topo2.id}',
                  'surface_key': f'surface-{topo2.surface.id}',
                  'title': 'Example 4 - Default',
                  'folder': False,
                  'version': '',
                  'publication_date': '',
                  'publication_authors': '',
                  'creator_name': topo2.creator.name,
                  'sharing_status': 'own',
                  'label': 'Example 4 - Default'}

    if is_authenticated:
        api_client.force_authenticate(user)

    response = api_client.get(reverse('manager:topography-api-list'))
    assert response.status_code == 405

    response = api_client.get(reverse('manager:topography-api-detail', kwargs=dict(pk=topo1.id)))
    if is_authenticated:
        assert response.status_code == 200
        data = json.loads(json.dumps(response.data))  # Convert OrderedDict to dict
        assert data == topo1_dict
    else:
        # Anonymous user does not have access by default
        assert response.status_code == 404

    response = api_client.get(reverse('manager:topography-api-detail', kwargs=dict(pk=topo2.id)))
    if is_authenticated:
        assert response.status_code == 200
        data = json.loads(json.dumps(response.data))  # Convert OrderedDict to dict
        assert data == topo2_dict
    else:
        # Anonymous user does not have access by default
        assert response.status_code == 404


@pytest.mark.django_db
def test_create_surface_routes(api_client, two_users, handle_usage_statistics):
    user1, user2 = two_users

    surface1_dict = {'label': 'Surface 1',
                     'name': 'Surface 1',
                     'title': 'Surface 1'}

    # Create as anonymous user should fail
    response = api_client.post(reverse('manager:surface-api-list'),
                               data=surface1_dict, format='json')
    assert response.status_code == 403

    assert Surface.objects.count() == 3

    # Create as user1 should succeed
    api_client.force_authenticate(user1)
    response = api_client.post(reverse('manager:surface-api-list'),
                               data=surface1_dict, format='json')
    assert response.status_code == 201

    assert Surface.objects.count() == 4
    _, _, _, s = Surface.objects.all()
    assert s.creator.name == user1.name


@pytest.mark.django_db
def test_delete_surface_routes(api_client, two_users, handle_usage_statistics):
    user1, user2 = two_users
    topo1, topo2, topo3 = Topography.objects.all()
    user = topo1.creator
    surface1 = topo1.surface
    surface2 = topo2.surface
    surface3 = topo3.surface

    # Delete as anonymous user should fail
    response = api_client.delete(reverse('manager:surface-api-detail', kwargs=dict(pk=surface1.id)),
                                 format='json')
    assert response.status_code == 403

    assert Surface.objects.count() == 3

    # Delete as user should succeed
    api_client.force_authenticate(user)
    response = api_client.delete(reverse('manager:surface-api-detail', kwargs=dict(pk=surface1.id)),
                                 format='json')
    assert response.status_code == 204  # Success, no content

    assert Surface.objects.count() == 2

    # Delete of a surface of another user should fail
    response = api_client.delete(reverse('manager:surface-api-detail', kwargs=dict(pk=surface2.id)),
                                 format='json')
    assert response.status_code == 404  # The user cannot see the surface, hence 404

    assert Surface.objects.count() == 2

    # Delete of a surface of another user should fail, even if shared
    surface2.share(user1, allow_change=False)
    response = api_client.delete(reverse('manager:surface-api-detail', kwargs=dict(pk=surface2.id)),
                                 format='json')
    assert response.status_code == 403  # The user can see the surface but not delete it, hence 403

    assert Surface.objects.count() == 2

    # Delete of a surface of another user should faile even if shared with write permission
    surface2.share(user1, allow_change=True)
    response = api_client.delete(reverse('manager:surface-api-detail', kwargs=dict(pk=surface2.id)),
                                 format='json')
    assert response.status_code == 403  # The user can see the surface but not delete it, hence 403
    assert Surface.objects.count() == 2

    # Delete of a published surface should always fail
    pub = surface3.publish('cc0', 'Bob')
    assert Surface.objects.count() == 3
    response = api_client.delete(reverse('manager:surface-api-detail', kwargs=dict(pk=pub.surface.id)),
                                 format='json')
    assert response.status_code == 403
    assert Surface.objects.count() == 3

    # Delete of a published surface should even fail for the owner
    api_client.force_authenticate(pub.surface.creator)
    response = api_client.delete(reverse('manager:surface-api-detail', kwargs=dict(pk=pub.surface.id)),
                                 format='json')
    assert response.status_code == 403
    assert Surface.objects.count() == 3


@pytest.mark.django_db
def test_delete_topography_routes(api_client, two_topos, handle_usage_statistics):
    topo1, topoe2 = two_topos
    user = topo1.creator

    # Delete as anonymous user should fail
    response = api_client.delete(reverse('manager:topography-api-detail', kwargs=dict(pk=topo1.id)),
                                 format='json')
    assert response.status_code == 403

    assert Topography.objects.count() == 2

    # Delete as user should succeed
    api_client.force_authenticate(user)
    response = api_client.delete(reverse('manager:topography-api-detail', kwargs=dict(pk=topo1.id)),
                                 format='json')
    assert response.status_code == 204  # Success, no content

    assert Topography.objects.count() == 1


@pytest.mark.django_db
def test_patch_surface_routes(api_client, two_topos, handle_usage_statistics):
    topo1, topo2 = two_topos
    user = topo1.creator
    surface1 = topo1.surface
    surface2 = topo2.surface

    new_name = 'My new name'

    # Patch as anonymous user should fail
    response = api_client.patch(reverse('manager:surface-api-detail', kwargs=dict(pk=surface1.id)),
                                data={'name': new_name},
                                format='json')
    assert response.status_code == 403

    assert Surface.objects.count() == 2

    # Patch as user should succeed
    api_client.force_authenticate(user)
    response = api_client.patch(reverse('manager:surface-api-detail', kwargs=dict(pk=surface1.id)),
                                data={'name': new_name},
                                format='json')
    assert response.status_code == 200  # Success, no content

    assert Surface.objects.count() == 2

    surface1, surface2 = Surface.objects.all()
    assert surface1.name == new_name


@pytest.mark.django_db
def test_patch_topography_routes(api_client, two_users, handle_usage_statistics):
    user1, user2 = two_users
    topo1, topo2, topo3 = Topography.objects.all()
    assert topo1.creator == user1

    new_name = 'My new name'

    # Patch as anonymous user should fail
    response = api_client.patch(reverse('manager:topography-api-detail', kwargs=dict(pk=topo1.id)),
                                data={'name': new_name},
                                format='json')
    assert response.status_code == 403

    assert Topography.objects.count() == 3

    # Patch as user should succeed
    api_client.force_authenticate(user1)
    response = api_client.patch(reverse('manager:topography-api-detail', kwargs=dict(pk=topo1.id)),
                                data={'name': new_name},
                                format='json')
    assert response.status_code == 200  # Success, no content

    assert Topography.objects.count() == 3
    topo1, topo2, topo3 = Topography.objects.all()
    assert topo1.name == new_name

    new_name = 'My second new name'

    # Patch of a topography of another user should fail
    response = api_client.patch(reverse('manager:topography-api-detail', kwargs=dict(pk=topo2.id)),
                                data={'name': new_name},
                                format='json')
    assert response.status_code == 404  # The user cannot see the surface, hence 404

    assert Topography.objects.count() == 3

    # Patch of a topography of another user should fail, even if shared
    topo2.surface.share(user1, allow_change=False)
    response = api_client.patch(reverse('manager:topography-api-detail', kwargs=dict(pk=topo2.id)),
                                data={'name': new_name},
                                format='json')
    assert response.status_code == 403  # The user can see the surface but not patch it, hence 403

    assert Topography.objects.count() == 3

    # Patch of a surface of another user should succeed if shared with write permission
    topo2.surface.share(user1, allow_change=True)
    response = api_client.patch(reverse('manager:topography-api-detail', kwargs=dict(pk=topo2.id)),
                                data={'name': new_name},
                                format='json')
    assert response.status_code == 200  # Success, no content
    assert Topography.objects.count() == 3
    topo1, topo2, topo3 = Topography.objects.all()
    assert topo2.name == new_name

    new_name = 'My third new name'

    # Patch of a published surface should always fail
    pub = topo3.surface.publish('cc0', 'Bob')
    topo_pub, = pub.surface.topography_set.all()
    assert Topography.objects.count() == 4
    response = api_client.patch(reverse('manager:topography-api-detail', kwargs=dict(pk=topo_pub.id)),
                                data={'name': new_name},
                                format='json')
    assert response.status_code == 403  # The user can see the surface but not patch it, hence 403
    assert Surface.objects.count() == 4

    # Delete of a published surface should even fail for the owner
    api_client.force_authenticate(pub.surface.creator)
    response = api_client.patch(reverse('manager:topography-api-detail', kwargs=dict(pk=topo_pub.id)),
                                data={'name': new_name},
                                format='json')
    assert response.status_code == 403  # The user can see the surface but not patch it, hence 403
    assert Surface.objects.count() == 4
