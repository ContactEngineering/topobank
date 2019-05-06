import pytest
from django.shortcuts import reverse
from .utils import SurfaceFactory, TopographyFactory, UserFactory
from topobank.utils import assert_in_content, assert_not_in_content


def test_individual_read_access_permissions(client, django_user_model):

    #
    # create database objects
    #
    username_1 = 'A'
    username_2 = 'B'
    password = 'secret'

    user_1 = django_user_model.objects.create_user(username=username_1, password=password)
    user_2 = django_user_model.objects.create_user(username=username_2, password=password)

    surface = SurfaceFactory(user=user_1)

    surface_detail_url = reverse('manager:surface-detail', kwargs=dict(pk=surface.pk))
    surface_update_url = reverse('manager:surface-update', kwargs=dict(pk=surface.pk))

    #
    # now user 1 has access to surface detail page
    #
    assert client.login(username=username_1, password=password)
    response = client.get(surface_detail_url)

    assert response.status_code == 200

    client.logout()

    #
    # User 2 has no access
    #
    assert client.login(username=username_2, password=password)
    response = client.get(surface_detail_url)

    assert response.status_code == 403 # forbidden

    client.logout()

    #
    # Now grant access and user 2 should be able to access
    #

    from guardian.shortcuts import assign_perm

    assign_perm('view_surface', user_2, surface)

    assert client.login(username=username_2, password=password)
    response = client.get(surface_detail_url)

    assert response.status_code == 200  # now it's okay

    #
    # Write access is still not possible
    #
    response = client.get(surface_update_url)

    assert response.status_code == 403  # forbidden

    client.logout()

def test_list_surface_permissions(client, django_user_model):

    #
    # create database objects
    #
    username = 'testuser'
    password = 'secret'

    user = django_user_model.objects.create_user(username=username, password=password)

    surface = SurfaceFactory(user=user)

    surface_detail_url = reverse('manager:surface-detail', kwargs=dict(pk=surface.pk))
    #
    # now user 1 has access to surface detail page
    #
    assert client.login(username=username, password=password)
    response = client.get(surface_detail_url)

    assert_in_content(response, "Permissions")
    assert_in_content(response, "You have the permission to share this surface")
    assert_in_content(response, "You have the permission to delete this surface")
    assert_in_content(response, "You have the permission to change this surface")
    assert_in_content(response, "You have the permission to view this surface")

@pytest.mark.django_db
def test_appearance_buttons_based_on_permissions(client):

    password = "secret"

    user1 = UserFactory(password=password)
    user2 = UserFactory(password=password)

    surface = SurfaceFactory(user=user1)
    surface_detail_url = reverse('manager:surface-detail', kwargs=dict(pk=surface.pk))
    surface_share_url = reverse('manager:surface-share', kwargs=dict(pk=surface.pk))
    surface_update_url = reverse('manager:surface-update', kwargs=dict(pk=surface.pk))
    surface_delete_url = reverse('manager:surface-delete', kwargs=dict(pk=surface.pk))

    surface.share(user2)

    topo = TopographyFactory(surface=surface, size_y=512)
    topo_detail_url = reverse('manager:topography-detail', kwargs=dict(pk=topo.pk))
    topo_update_url = reverse('manager:topography-update', kwargs=dict(pk=topo.pk))
    topo_delete_url = reverse('manager:topography-delete', kwargs=dict(pk=topo.pk))

    #
    # first user can see links for editing and deletion
    #
    assert client.login(username=user1.username, password=password)

    response = client.get(surface_detail_url)
    assert_in_content(response, surface_share_url)
    assert_in_content(response, surface_update_url)
    assert_in_content(response, surface_delete_url)

    response = client.get(topo_detail_url)
    assert_in_content(response, topo_update_url)
    assert_in_content(response, topo_delete_url)

    client.logout()
    #
    # Second user can't see those links, only view stuff
    #
    assert client.login(username=user2.username, password=password)

    response = client.get(surface_detail_url)
    assert_not_in_content(response, surface_share_url)
    assert_not_in_content(response, surface_update_url)
    assert_not_in_content(response, surface_delete_url)

    response = client.get(topo_detail_url)
    assert_not_in_content(response, topo_update_url)
    assert_not_in_content(response, topo_delete_url)

    #
    # When allowing to change, the second user should see links
    # for edit as well, for topography also "delete" and "add"
    #
    surface.share(user2, allow_change=True)

    response = client.get(surface_detail_url)
    assert_not_in_content(response, surface_share_url) # still not share
    assert_in_content(response, surface_update_url)
    assert_not_in_content(response, surface_delete_url) # still not delete

    response = client.get(topo_detail_url)
    assert_in_content(response, topo_update_url)
    assert_in_content(response, topo_delete_url)

