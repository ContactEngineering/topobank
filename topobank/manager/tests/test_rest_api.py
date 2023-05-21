import json

import pytest

from django.shortcuts import reverse

from .utils import two_topos


@pytest.mark.django_db
def test_topography_routes(api_client, two_topos):
    topo1, topo2 = two_topos
    topo1_dict = {'id': topo1.id,
                  'type': 'topography',
                  'name': 'Example 3 - ZSensor',
                  'creator': 'http://testserver/users/testuser/',
                  'description': 'description1',
                  'tags': [],
                  'urls': {
                      'select': f'/manager/api/selection/topography/{topo1.id}/select/',
                      'unselect': f'/manager/api/selection/topography/{topo1.id}/unselect/'},
                  'selected': False,
                  'key': f'topography-{topo1.id}',
                  'surface_key': f'surface-{topo1.surface.id}',
                  'title': 'Example 3 - ZSensor',
                  'folder': False,
                  'version': '',
                  'publication_date': '',
                  'publication_authors': '',
                  'creator_name': topo1.creator.name,
                  'sharing_status': 'shared',
                  'label': 'Example 3 - ZSensor'}
    topo2_dict = {'id': topo2.id,
                  'type': 'topography',
                  'name': 'Example 4 - Default',
                  'creator': 'http://testserver/users/testuser/',
                  'description': 'description2',
                  'tags': [],
                  'urls': {
                      'select': f'/manager/api/selection/topography/{topo2.id}/select/',
                      'unselect': f'/manager/api/selection/topography/{topo2.id}/unselect/'},
                  'selected': False,
                  'key': f'topography-{topo2.id}',
                  'surface_key': f'surface-{topo2.surface.id}',
                  'title': 'Example 4 - Default',
                  'folder': False,
                  'version': '',
                  'publication_date': '',
                  'publication_authors': '',
                  'creator_name': topo2.creator.name,
                  'sharing_status': 'shared',
                  'label': 'Example 4 - Default'}

    response = api_client.get(reverse('manager:topography-api-list'))
    data = json.loads(json.dumps(response.data))  # Convert OrderedDict to dict
    assert data == [topo1_dict, topo2_dict]

    response = api_client.get(reverse('manager:topography-api-detail', kwargs=dict(pk=topo1.id)))
    data = json.loads(json.dumps(response.data))  # Convert OrderedDict to dict
    assert response.data == topo1_dict

    response = api_client.get(reverse('manager:topography-api-detail', kwargs=dict(pk=topo2.id)))
    data = json.loads(json.dumps(response.data))  # Convert OrderedDict to dict
    assert response.data == topo2_dict
