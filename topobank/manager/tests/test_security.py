from pathlib import Path

import pytest
from django.urls import reverse
from django.contrib.auth.models import Permission

from .utils import FIXTURE_DIR
from ..models import Surface, Topography
from topobank.utils import assert_in_content, assert_redirects

@pytest.mark.django_db
def test_prevent_surface_access_by_other_user(client, django_user_model):

    surface_id = 1
    username1 = 'testuser1'
    password1 = 'abcd$1234'
    username2 = 'testuser2'
    password2 = 'abcd$5678'

    #
    # Create surface of user 1
    #
    user1 = django_user_model.objects.create_user(username=username1, password=password1)

    surface = Surface.objects.create(id=surface_id, name="Surface 1", creator=user1)
    assert surface.id == surface_id
    surface.save()

    #
    # Login as user 2
    #
    user2 = django_user_model.objects.create_user(username=username2, password=password2)
    assert client.login(username=username2, password=password2)

    # give both user permissions to skip all terms, we want to test independently from this
    skip_perm = Permission.objects.get(codename='can_skip_terms')
    user1.user_permissions.add(skip_perm)
    user2.user_permissions.add(skip_perm)

    #
    # As user 2, try to access surface from user 1 with various views
    #
    # Each time, this should redirect to an access denied page
    #
    response = client.get(reverse('manager:surface-detail', kwargs=dict(pk=surface_id)))
    assert response.status_code == 403

    response = client.get(reverse('manager:surface-update', kwargs=dict(pk=surface_id)))
    assert response.status_code == 403

    response = client.get(reverse('manager:surface-delete', kwargs=dict(pk=surface_id)))
    assert response.status_code == 403

@pytest.mark.django_db
def test_prevent_topography_access_by_other_user(client, django_user_model, mocker):

    surface_id = 1
    username1 = 'testuser1'
    password1 = 'abcd$1234'
    username2 = 'testuser2'
    password2 = 'abcd$5678'

    #
    # Create surface of user 1
    #
    user1 = django_user_model.objects.create_user(username=username1, password=password1)

    surface = Surface.objects.create(id=surface_id, name="Surface 1", creator=user1)
    assert surface.id == surface_id
    surface.save()

    #
    # Mock a topography
    #
    input_file_path = Path(FIXTURE_DIR+'/example3.di')

    # prevent signals when creating topography
    with mocker.patch('django.db.models.signals.pre_save.send'):
        with mocker.patch('django.db.models.signals.post_save.send'):
            topography = Topography.objects.create(name="topo", surface=surface, measurement_date='2018-01-01',
                                                   data_source=0,
                                                   size_x=1, size_y=1,
                                                   resolution_x=1, resolution_y=1,
                                                   datafile=str(input_file_path))
    topography_id = topography.id

    #
    # Login as user 2
    #
    django_user_model.objects.create_user(username=username2, password=password2)
    assert client.login(username=username2, password=password2)

    #
    # As user 2, try to access topography from user 1 with various views
    #
    # Each time, this should redirect to an access denied page
    #
    response = client.get(reverse('manager:topography-detail', kwargs=dict(pk=topography_id)))
    assert response.status_code == 403

    response = client.get(reverse('manager:topography-update', kwargs=dict(pk=topography_id)))
    assert response.status_code == 403

    response = client.get(reverse('manager:topography-delete', kwargs=dict(pk=topography_id)))
    assert response.status_code == 403


@pytest.mark.django_db
def test_pagenotfound__if_surface_does_not_exist(client, django_user_model):

    username = 'testuser1'
    password = 'abcd$1234'

    django_user_model.objects.create_user(username=username, password=password)

    assert client.login(username=username, password=password)

    response = client.get(reverse('manager:surface-detail', kwargs=dict(pk=999)))
    assert response.status_code == 404


@pytest.mark.django_db
def test_pagenotfound_if_topography_does_not_exist(client, django_user_model):
    username = 'testuser1'
    password = 'abcd$1234'

    django_user_model.objects.create_user(username=username, password=password)

    assert client.login(username=username, password=password)

    response = client.get(reverse('manager:topography-detail', kwargs=dict(pk=999)))
    assert response.status_code == 404

