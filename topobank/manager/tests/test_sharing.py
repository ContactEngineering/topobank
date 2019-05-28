import pytest
from pathlib import Path
import datetime
from django.shortcuts import reverse
from bs4 import BeautifulSoup

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

    surface = SurfaceFactory(creator=user_1)

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

@pytest.mark.django_db
def test_list_surface_permissions(client):

    #
    # create database objects
    #
    password = 'secret'

    user1 = UserFactory(password=password)
    user2 = UserFactory(name="Bob Marley")
    user3 = UserFactory(name="Alice Cooper")

    surface = SurfaceFactory(creator=user1)
    surface.share(user2)
    surface.share(user3, allow_change=True)

    surface_detail_url = reverse('manager:surface-detail', kwargs=dict(pk=surface.pk))

    #
    # now user 1 has access to surface detail page
    #
    assert client.login(username=user1.username, password=password)
    response = client.get(surface_detail_url)

    assert_in_content(response, "Permissions")

    # related to user 1
    assert_in_content(response, "You have the permission to share this surface")
    assert_in_content(response, "You have the permission to delete this surface")
    assert_in_content(response, "You have the permission to change this surface")
    assert_in_content(response, "You have the permission to view this surface")

    # related to user 2
    assert_in_content(response, "Bob Marley hasn&#39;t the permission to share this surface")
    assert_in_content(response, "Bob Marley hasn&#39;t the permission to delete this surface")
    assert_in_content(response, "Bob Marley hasn&#39;t the permission to change this surface")
    assert_in_content(response, "Bob Marley has the permission to view this surface")

    # related to user 3
    assert_in_content(response, "Alice Cooper hasn&#39;t the permission to share this surface")
    assert_in_content(response, "Alice Cooper hasn&#39;t the permission to delete this surface")
    assert_in_content(response, "Alice Cooper has the permission to change this surface")
    assert_in_content(response, "Alice Cooper has the permission to view this surface")


@pytest.mark.django_db
def test_appearance_buttons_based_on_permissions(client):

    password = "secret"

    user1 = UserFactory(password=password)
    user2 = UserFactory(password=password)

    surface = SurfaceFactory(creator=user1)
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

def _parse_html_table(table):
    """Return list of lists with cell texts.

    :param table: beautifulsoup tag with table element
    """
    rows = table.findAll("tr")

    data = []
    for row in rows:

        tds = row.findAll("td")
        ths = row.findAll("th")

        if len(ths) > 0:
            tmp = [th.text.strip() for th in ths]
        else:
            tmp = [td.text.strip() for td in tds]

        data.append(tmp)

    return data

@pytest.mark.django_db
def test_link_for_sharing_info(client):
    password = "secret"
    user = UserFactory(password=password)
    assert client.login(username=user.username, password=password)

    response = client.get(reverse('home'))

    assert response.status_code == 200
    assert_in_content(response, reverse('manager:sharing-info'))

@pytest.mark.django_db
def test_sharing_info_table(client):
    password = "secret"

    user1 = UserFactory(password=password)
    user2 = UserFactory(password=password)
    user3 = UserFactory(password=password)

    surface1 = SurfaceFactory(creator=user1)
    surface2 = SurfaceFactory(creator=user2)

    surface1.share(user2, allow_change=False)
    surface1.share(user3, allow_change=True)

    surface2.share(user1)

    TopographyFactory(surface=surface1) # one topography for surface 1

    FALSE_CHAR = '✘'
    TRUE_CHAR = '✔'

    #
    # Test for user 1
    #
    assert client.login(username=user1.username, password=password)

    response = client.get(reverse('manager:sharing-info'))

    assert response.status_code == 200

    soup = BeautifulSoup(response.content)

    table = soup.find("table")

    data = _parse_html_table(table)

    import pprint
    pprint.pprint(data)

    assert data == [
        ['Surface', '# Topographies', 'Created by', 'Shared with', 'Allow change', ''],
        [surface1.name, '1', 'You', user2.name, FALSE_CHAR, ''],
        [surface1.name, '1', 'You', user3.name, TRUE_CHAR, ''],
        [surface2.name, '0', user2.name, 'You', FALSE_CHAR, ''],
    ]

    client.logout()


    #
    # Test for user 2
    #
    assert client.login(username=user2.username, password=password)

    response = client.get(reverse('manager:sharing-info'))

    assert response.status_code == 200

    soup = BeautifulSoup(response.content)

    table = soup.find("table")

    data = _parse_html_table(table)

    import pprint
    pprint.pprint(data)

    assert data == [
        ['Surface', '# Topographies', 'Created by', 'Shared with', 'Allow change', ''],
        [surface1.name, '1', user1.name, 'You', FALSE_CHAR, ''],
        [surface2.name, '0', 'You', user1.name, FALSE_CHAR, ''],
    ]

    client.logout()

    #
    # Test for user 3
    #
    assert client.login(username=user3.username, password=password)

    response = client.get(reverse('manager:sharing-info'))

    assert response.status_code == 200

    soup = BeautifulSoup(response.content)

    table = soup.find("table")

    data = _parse_html_table(table)

    import pprint
    pprint.pprint(data)

    assert data == [
        ['Surface', '# Topographies', 'Created by', 'Shared with', 'Allow change', ''],
        [surface1.name, '1', user1.name, 'You', TRUE_CHAR, ''],
    ]

    client.logout()

    #
    # Now first user removes share for user 3
    #
    assert client.login(username=user1.username, password=password)

    response = client.post(reverse('manager:sharing-info'),
                           {
                               'selected': '{},{}'.format(surface1.id, user3.id),
                               'unshare': 'unshare'
                           })

    assert response.status_code == 200

    soup = BeautifulSoup(response.content)

    table = soup.find("table")

    data = _parse_html_table(table)

    import pprint
    pprint.pprint(data)

    assert data == [
        ['Surface', '# Topographies', 'Created by', 'Shared with', 'Allow change', ''],
        [surface1.name, '1', 'You', user2.name, FALSE_CHAR, ''],
        [surface2.name, '0', user2.name, 'You', FALSE_CHAR, ''],
    ]

    #
    # Next user 1 allows changing surface 1 for user 2
    #
    response = client.post(reverse('manager:sharing-info'),
                           {
                               'selected': '{},{}'.format(surface1.id, user2.id),
                               'allow_change': 'allow_change'
                           })

    assert response.status_code == 200

    soup = BeautifulSoup(response.content)

    table = soup.find("table")

    data = _parse_html_table(table)

    import pprint
    pprint.pprint(data)

    assert data == [
        ['Surface', '# Topographies', 'Created by', 'Shared with', 'Allow change', ''],
        [surface1.name, '1', 'You', user2.name, TRUE_CHAR, ''],
        [surface2.name, '0', user2.name, 'You', FALSE_CHAR, ''],
    ]

    client.logout()

    #
    # This is also visible for user2
    #
    assert client.login(username=user2.username, password=password)

    response = client.get(reverse('manager:sharing-info'))

    assert response.status_code == 200

    soup = BeautifulSoup(response.content)

    table = soup.find("table")

    data = _parse_html_table(table)

    import pprint
    pprint.pprint(data)

    assert data == [
        ['Surface', '# Topographies', 'Created by', 'Shared with', 'Allow change', ''],
        [surface1.name, '1', user1.name, 'You', TRUE_CHAR, ''],
        [surface2.name, '0', 'You', user1.name, FALSE_CHAR, ''],
    ]

    client.logout()

@pytest.mark.django_db
def test_upload_topography_for_shared_surface(client):

    input_file_path = Path('topobank/manager/fixtures/example3.di') # TODO use standardized way to find files
    description = "test description"

    password = 'abcd$1234'

    user1 = UserFactory(password=password)
    user2 = UserFactory(password=password)

    surface = SurfaceFactory(creator=user1)
    surface.share(user2) # first without allowing change


    assert client.login(username=user2.username, password=password)

    #
    # open first step of wizard: file upload
    #
    with open(str(input_file_path), mode='rb') as fp:

        response = client.post(reverse('manager:topography-create',
                                       kwargs=dict(surface_id=surface.id)),
                               data={
                                'topography_create_wizard-current_step': 'upload',
                                'upload-datafile': fp,
                                'upload-surface': surface.id,
                               }, follow=True)

    assert response.status_code == 403 # user2 is not allowed to change

    #
    # Now allow to change and get response again
    #
    surface.share(user2, allow_change=True)

    with open(str(input_file_path), mode='rb') as fp:
        response = client.post(reverse('manager:topography-create',
                                       kwargs=dict(surface_id=surface.id)),
                               data={
                                   'topography_create_wizard-current_step': 'upload',
                                   'upload-datafile': fp,
                                   'upload-surface': surface.id,
                               }, follow=True)

    assert response.status_code == 200

    #
    # check contents of second page
    #

    # now we should be on the page with second step
    assert b"Step 2 of 3" in response.content, "Errors:"+str(response.context['form'].errors)

    # we should have two datasources as options, "ZSensor" and "Height"

    assert b'<option value="0">ZSensor</option>' in response.content
    assert b'<option value="1">Height</option>' in response.content

    assert response.context['form'].initial['name'] == 'example3.di'

    #
    # Send data for second page
    #
    response = client.post(reverse('manager:topography-create',
                                   kwargs=dict(surface_id=surface.id)),
                           data={
                            'topography_create_wizard-current_step': 'metadata',
                            'metadata-name': 'topo1',
                            'metadata-measurement_date': '2018-06-21',
                            'metadata-data_source': 0,
                            'metadata-description': description,
                           })

    assert response.status_code == 200
    assert b"Step 3 of 3" in response.content, "Errors:" + str(response.context['form'].errors)

    #
    # Send data for third page
    #
    response = client.post(reverse('manager:topography-create',
                                   kwargs=dict(surface_id=surface.id)),
                           data={
                               'topography_create_wizard-current_step': 'units2D',
                               'units2D-size_x': '9000',
                               'units2D-size_y': '9000',
                               'units2D-unit': 'nm',
                               'units2D-height_scale': 0.3,
                               'units2D-detrend_mode': 'height',
                               'units2D-resolution_x': 256,
                               'units2D-resolution_y': 256,
                           }, follow=True)

    assert response.status_code == 200
    # assert reverse('manager:topography-detail', kwargs=dict(pk=1)) == response.url
    # export_reponse_as_html(response)

    assert 'form' not in response.context, "Errors:" + str(response.context['form'].errors)

    topos = surface.topography_set.all()

    assert len(topos) == 1

    t = topos[0]

    assert t.measurement_date == datetime.date(2018,6,21)
    assert t.description == description
    assert "example3" in t.datafile.name
    assert 256 == t.resolution_x
    assert 256 == t.resolution_y
    assert t.creator == user2

    #
    # Test little badge which shows who uploaded data
    #
    response = client.get(reverse('manager:topography-detail', kwargs=dict(pk=t.pk)))
    assert response.status_code == 200

    assert_in_content(response, 'uploaded by you')

    client.logout()
    assert client.login(username=user1.username, password=password)
    response = client.get(reverse('manager:topography-detail', kwargs=dict(pk=t.pk)))
    assert response.status_code == 200

    assert_in_content(response, 'uploaded by {}'.format(user2.name))
    client.logout()


