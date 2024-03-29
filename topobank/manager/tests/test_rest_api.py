import json

import numpy
import pytest
from django.shortcuts import reverse
from guardian.shortcuts import get_anonymous_user

from ...manager.models import Surface, Topography


@pytest.mark.django_db
@pytest.mark.parametrize('is_authenticated,with_children', [[True, False],
                                                            [False, False],
                                                            [True, True]])
def test_surface_retrieve_routes(api_client, is_authenticated, with_children, two_topos, handle_usage_statistics):
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
                     'creator': f'http://testserver/users/api/user/{user.id}/',
                     'description': '',
                     'name': 'Surface 1',
                     'id': surface1.id,
                     'tags': [],
                     'url': f'http://testserver/manager/api/surface/{surface1.id}/',
                     'creation_datetime': surface1.creation_datetime.astimezone().isoformat(),
                     'modification_datetime': surface1.modification_datetime.astimezone().isoformat(),
                     'topography_set': [{'bandwidth_lower': None,
                                         'bandwidth_upper': None,
                                         'creator': f'http://testserver/users/api/user/{user.id}/',
                                         'datafile_format': None,
                                         'description': 'description1',
                                         'detrend_mode': 'height',
                                         'fill_undefined_data_mode': 'do-not-fill',
                                         'has_undefined_data': None,
                                         'height_scale': 0.296382712790741,
                                         'height_scale_editable': False,
                                         'instrument_name': '',
                                         'instrument_parameters': {},
                                         'instrument_type': 'undefined',
                                         'is_periodic': False,
                                         'is_periodic_editable': True,
                                         'measurement_date': '2018-01-01',
                                         'name': 'Example 3 - ZSensor',
                                         'resolution_x': 256,
                                         'resolution_y': 256,
                                         'short_reliability_cutoff': None,
                                         'size_editable': True,
                                         'size_x': 10.0,
                                         'size_y': 10.0,
                                         'surface': f'http://testserver/manager/api/surface/{surface1.id}/',
                                         'unit': 'µm',
                                         'unit_editable': False,
                                         'url': f'http://testserver/manager/api/topography/{topo1.id}/',
                                         'duration': None,
                                         'error': None,
                                         'id': topo1.id,
                                         'upload_instructions': None,
                                         'squeezed_datafile': None,
                                         'tags': [],
                                         'task_progress': 0.0,
                                         'task_state': 'no',
                                         'thumbnail': None,
                                         'channel_names': [],
                                         'data_source': 0,
                                         'is_metadata_complete': True,
                                         'creation_datetime': topo1.creation_datetime.astimezone().isoformat(),
                                         'modification_datetime': topo1.modification_datetime.astimezone().isoformat(),
                                         }]}
    if hasattr(Surface, 'publication'):
        surface1_dict['publication'] = None
    surface2_dict = {'category': None,
                     'creator': f'http://testserver/users/api/user/{user.id}/',
                     'description': '',
                     'name': 'Surface 2',
                     'id': surface2.id,
                     'tags': [],
                     'url': f'http://testserver/manager/api/surface/{surface2.id}/',
                     'creation_datetime': surface2.creation_datetime.astimezone().isoformat(),
                     'modification_datetime': surface2.modification_datetime.astimezone().isoformat(),
                     'topography_set': [{'bandwidth_lower': None,
                                         'bandwidth_upper': None,
                                         'creator': f'http://testserver/users/api/user/{user.id}/',
                                         'datafile_format': None,
                                         'description': 'description2',
                                         'detrend_mode': 'height',
                                         'fill_undefined_data_mode': 'do-not-fill',
                                         'has_undefined_data': None,
                                         'height_scale': 2.91818e-08,
                                         'height_scale_editable': False,
                                         'instrument_name': '',
                                         'instrument_parameters': {},
                                         'instrument_type': 'undefined',
                                         'is_periodic': False,
                                         'is_periodic_editable': True,
                                         'measurement_date': '2018-01-02',
                                         'name': 'Example 4 - Default',
                                         'resolution_x': 305,
                                         'resolution_y': 75,
                                         'short_reliability_cutoff': None,
                                         'size_editable': False,
                                         'size_x': 112.80791,
                                         'size_y': 27.73965,
                                         'surface': f'http://testserver/manager/api/surface/{surface2.id}/',
                                         'unit': 'µm',
                                         'unit_editable': False,
                                         'url': f'http://testserver/manager/api/topography/{topo2.id}/',
                                         'duration': None,
                                         'error': None,
                                         'id': topo2.id,
                                         'upload_instructions': None,
                                         'squeezed_datafile': None,
                                         'tags': [],
                                         'task_progress': 0.0,
                                         'task_state': 'no',
                                         'thumbnail': None,
                                         'channel_names': [],
                                         'data_source': 0,
                                         'is_metadata_complete': True,
                                         'creation_datetime': topo2.creation_datetime.astimezone().isoformat(),
                                         'modification_datetime': topo2.modification_datetime.astimezone().isoformat(),
                                         }]}
    if hasattr(Surface, 'publication'):
        surface2_dict['publication'] = None

    if not with_children:
        del surface1_dict['topography_set']
        del surface2_dict['topography_set']

    if is_authenticated:
        api_client.force_authenticate(user)

    response = api_client.get(reverse('manager:surface-api-list'))
    assert response.status_code == 405

    url = reverse('manager:surface-api-detail', kwargs=dict(pk=surface1.id))
    if with_children:
        url += '?children=yes'
    response = api_client.get(url)
    if is_authenticated:
        assert response.status_code == 200
        data = json.loads(json.dumps(response.data))  # Convert OrderedDict to dict
        if 'topography_set' in data:
            for t in data['topography_set']:
                del t['datafile']  # datafile has an S3 hash which is difficult to mock
        assert data == surface1_dict
    else:
        # Anonymous user does not have access by default
        assert response.status_code == 404

    url = reverse('manager:surface-api-detail', kwargs=dict(pk=surface2.id))
    if with_children:
        url += '?children=yes'
    response = api_client.get(url)
    if is_authenticated:
        assert response.status_code == 200
        data = json.loads(json.dumps(response.data))  # Convert OrderedDict to dict
        if 'topography_set' in data:
            for t in data['topography_set']:
                del t['datafile']  # datafile has an S3 hash which is difficult to mock
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

    topo1_dict = {'bandwidth_lower': None,
                  'bandwidth_upper': None,
                  'creator': f'http://testserver/users/api/user/{user.id}/',
                  'datafile_format': None,
                  'description': 'description1',
                  'detrend_mode': 'height',
                  'fill_undefined_data_mode': 'do-not-fill',
                  'has_undefined_data': None,
                  'height_scale': 0.296382712790741,
                  'height_scale_editable': False,
                  'instrument_name': '',
                  'instrument_parameters': {},
                  'instrument_type': 'undefined',
                  'is_periodic': False,
                  'is_periodic_editable': True,
                  'measurement_date': '2018-01-01',
                  'name': 'Example 3 - ZSensor',
                  'resolution_x': 256,
                  'resolution_y': 256,
                  'short_reliability_cutoff': None,
                  'size_editable': True,
                  'size_x': 10.0,
                  'size_y': 10.0,
                  'surface': f'http://testserver/manager/api/surface/{topo1.surface.id}/',
                  'unit': 'µm',
                  'unit_editable': False,
                  'url': f'http://testserver/manager/api/topography/{topo1.id}/',
                  'tags': [],
                  'task_progress': 0.0,
                  'task_state': 'pe',
                  'thumbnail': None,
                  'squeezed_datafile': None,
                  'upload_instructions': None,
                  'is_metadata_complete': True,
                  'id': topo1.id,
                  'error': None,
                  'duration': None,
                  'data_source': 0,
                  'channel_names': [],
                  'creation_datetime': topo1.creation_datetime.astimezone().isoformat(),
                  'modification_datetime': topo1.modification_datetime.astimezone().isoformat(),
                  }
    topo2_dict = {'bandwidth_lower': None,
                  'bandwidth_upper': None,
                  'creator': f'http://testserver/users/api/user/{user.id}/',
                  'datafile_format': None,
                  'description': 'description2',
                  'detrend_mode': 'height',
                  'fill_undefined_data_mode': 'do-not-fill',
                  'has_undefined_data': None,
                  'height_scale': 2.91818e-08,
                  'height_scale_editable': False,
                  'instrument_name': '',
                  'instrument_parameters': {},
                  'instrument_type': 'undefined',
                  'is_periodic': False,
                  'is_periodic_editable': True,
                  'measurement_date': '2018-01-02',
                  'name': 'Example 4 - Default',
                  'resolution_x': 305,
                  'resolution_y': 75,
                  'short_reliability_cutoff': None,
                  'size_editable': False,
                  'size_x': 112.80791,
                  'size_y': 27.73965,
                  'surface': f'http://testserver/manager/api/surface/{topo2.surface.id}/',
                  'unit': 'µm',
                  'unit_editable': False,
                  'url': f'http://testserver/manager/api/topography/{topo2.id}/',
                  'tags': [],
                  'task_progress': 0.0,
                  'task_state': 'pe',
                  'thumbnail': None,
                  'squeezed_datafile': None,
                  'upload_instructions': None,
                  'is_metadata_complete': True,
                  'id': topo2.id,
                  'error': None,
                  'duration': None,
                  'data_source': 0,
                  'channel_names': [],
                  'creation_datetime': topo2.creation_datetime.astimezone().isoformat(),
                  'modification_datetime': topo2.modification_datetime.astimezone().isoformat(),
                  }

    if is_authenticated:
        api_client.force_authenticate(user)

    response = api_client.get(reverse('manager:topography-api-list'))
    assert response.status_code == 405

    response = api_client.get(reverse('manager:topography-api-detail', kwargs=dict(pk=topo1.id)))
    if is_authenticated:
        assert response.status_code == 200
        data = json.loads(json.dumps(response.data))  # Convert OrderedDict to dict
        del data['datafile']  # datafile has an S3 hash which is difficult to mock
        # topo1 is updated but the get command, because it is triggering file inspection
        topo1 = Topography.objects.get(pk=topo1.id)
        topo1_dict['modification_datetime'] = topo1.modification_datetime.astimezone().isoformat()
        assert data == topo1_dict
    else:
        # Anonymous user does not have access by default
        assert response.status_code == 404

    response = api_client.get(reverse('manager:topography-api-detail', kwargs=dict(pk=topo2.id)))
    if is_authenticated:
        assert response.status_code == 200
        data = json.loads(json.dumps(response.data))  # Convert OrderedDict to dict
        del data['datafile']  # datafile has an S3 hash which is difficult to mock
        # topo2 is updated but the get command, because it is triggering file inspection
        topo2 = Topography.objects.get(pk=topo2.id)
        topo2_dict['modification_datetime'] = topo2.modification_datetime.astimezone().isoformat()
        assert data == topo2_dict
    else:
        # Anonymous user does not have access by default
        assert response.status_code == 404


@pytest.mark.django_db
def test_create_surface_routes(api_client, two_users, handle_usage_statistics):
    user1, user2 = two_users

    surface1_dict = {'name': 'Surface 1',
                     'description': 'This is surface 1'}

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


@pytest.mark.django_db(transaction=True)
def test_delete_surface_routes(api_client, two_users, handle_usage_statistics):
    user1, user2 = two_users
    topo1, topo2, topo3 = Topography.objects.all()
    user = topo1.creator
    surface1 = topo1.surface
    surface2 = topo2.surface

    # Delete as anonymous user should fail
    response = api_client.delete(reverse('manager:surface-api-detail', kwargs=dict(pk=surface1.id)))
    assert response.status_code == 403

    assert Surface.objects.count() == 3

    # Delete as user should succeed
    api_client.force_authenticate(user)
    response = api_client.delete(reverse('manager:surface-api-detail', kwargs=dict(pk=surface1.id)))
    assert response.status_code == 204  # Success, no content

    assert Surface.objects.count() == 2

    # Delete of a surface of another user should fail
    response = api_client.delete(reverse('manager:surface-api-detail', kwargs=dict(pk=surface2.id)))
    assert response.status_code == 404  # The user cannot see the surface, hence 404

    assert Surface.objects.count() == 2

    # Delete of a surface of another user should fail, even if shared
    surface2.set_permissions(user1, 'view')
    response = api_client.delete(reverse('manager:surface-api-detail', kwargs=dict(pk=surface2.id)))
    assert response.status_code == 403  # The user can see the surface but not delete it, hence 403

    assert Surface.objects.count() == 2

    # Delete of a surface of another user should fail even if shared with write permission
    surface2.set_permissions(user1, 'edit')
    response = api_client.delete(reverse('manager:surface-api-detail', kwargs=dict(pk=surface2.id)))
    assert response.status_code == 403  # The user can see the surface but not delete it, hence 403
    assert Surface.objects.count() == 2

    # Delete of a surface of another user is possible with full access
    surface2.set_permissions(user1, 'full')
    response = api_client.delete(reverse('manager:surface-api-detail', kwargs=dict(pk=surface2.id)))
    assert response.status_code == 204  # The user can see the surface but not delete it, hence 403
    assert Surface.objects.count() == 1


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

    assert surface1.modification_datetime > surface1.creation_datetime


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
    assert topo1.modification_datetime > topo1.creation_datetime

    new_name = 'My second new name'

    # Patch of a topography of another user should fail
    response = api_client.patch(reverse('manager:topography-api-detail', kwargs=dict(pk=topo2.id)),
                                data={'name': new_name},
                                format='json')
    assert response.status_code == 404  # The user cannot see the surface, hence 404

    assert Topography.objects.count() == 3

    # Patch of a topography of another user should fail, even if shared
    topo2.surface.set_permissions(user1, 'view')
    response = api_client.patch(reverse('manager:topography-api-detail', kwargs=dict(pk=topo2.id)),
                                {'name': new_name})
    assert response.status_code == 403  # The user can see the surface but not patch it, hence 403

    assert Topography.objects.count() == 3

    # Patch of a surface of another user should succeed if shared with write permission
    topo2.surface.set_permissions(user1, 'edit')
    response = api_client.patch(reverse('manager:topography-api-detail', kwargs=dict(pk=topo2.id)),
                                {'name': new_name})
    assert response.status_code == 200  # Success, no content
    assert Topography.objects.count() == 3
    topo1, topo2, topo3 = Topography.objects.all()
    assert topo2.name == new_name

    # Patching surface field of a topography should fail
    response = api_client.patch(reverse('manager:topography-api-detail',
                                        kwargs=dict(pk=topo2.id)),
                                {'surface': reverse('manager:surface-api-detail',
                                                    kwargs=dict(pk=topo1.surface.id))})
    assert response.status_code == 400  # The user can see the surface but not patch it, hence 400
    assert Topography.objects.count() == 3
    topo1, topo2, topo3 = Topography.objects.all()
    assert topo2.name == new_name
    surface1, surface2, surface3 = Surface.objects.all()
    assert surface1.topography_set.count() == 1
    assert surface2.topography_set.count() == 1
    assert surface3.topography_set.count() == 1


def test_versions(api_client):
    response = api_client.get(reverse('manager:versions'))
    assert response.data['numpy'] == {
        'version': numpy.__version__,
        'license': 'BSD 3-Clause',
        'homepage': 'https://numpy.org/'
    }


@pytest.mark.django_db
def test_statistics(api_client, two_users, handle_usage_statistics):
    response = api_client.get(reverse('manager:statistics'))
    assert response.data['nb_users'] == 2
    assert response.data['nb_surfaces'] == 3
    assert response.data['nb_topographies'] == 3
