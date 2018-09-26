
import pytest
from django.shortcuts import reverse

from pathlib import Path
import datetime

from ..models import Topography, Surface
from .utils import two_topos

def export_reponse_as_html(response, fname='/tmp/response.html'):
    """
    Helper function which can be used for debugging.

    :param response: HTTPResponse
    :param fname: name of HTML output file
    """
    f = open(fname, mode='w')

    f.write(response.content.decode('utf-8').replace('\\n','\n'))
    f.close()

#
# Different formats are handled by PyCo
# and should be tested there
#
@pytest.mark.django_db
def test_upload_topography(client, django_user_model):

    # input_file_path = Path('../../../PyCo-web/PyCo_app/data/gain_control_uncd_dlc_4.004')
    input_file_path = Path('topobank/manager/fixtures/example3.di') # TODO use standardized way to find files
    description = "test description"

    username = 'testuser'
    password = 'abcd$1234'

    user = django_user_model.objects.create_user(username=username, password=password)

    assert client.login(username=username, password=password)

    # first create a surface
    response = client.post(reverse('manager:surface-create'),
                               data={
                                'name': 'surface1',
                                'user': user.id,
                               }, follow=True)
    assert response.status_code == 200

    surface = Surface.objects.get(name='surface1')

    #
    # open first step of wizard: file upload
    #
    with open(str(input_file_path), mode='rb') as fp:

        response = client.post(reverse('manager:topography-create',
                                       kwargs=dict(surface_id=surface.id)),
                               data={
                                'topography_create_wizard-current_step': '0',
                                '0-datafile': fp,
                               }, follow=True)

    assert response.status_code == 200
    # now we should be on the page with second step
    assert b"Step 2 of 3" in response.content, "Errors:"+str(response.context['form'].errors)

    # we should have two datasources as options, "ZSensor" and "Height"

    assert b'<option value="0">ZSensor</option>' in response.content
    assert b'<option value="1">Height</option>' in response.content

    #
    # Send data for second page
    #
    response = client.post(reverse('manager:topography-create',
                                   kwargs=dict(surface_id=surface.id)),
                           data={
                            'topography_create_wizard-current_step': '1',
                            '1-name': 'topo1',
                            '1-measurement_date': '2018-06-21',
                            '1-datafile': str(input_file_path),
                            '1-data_source': 0,
                            '1-description': description,
                            '1-surface': surface.id,
                           })

    assert response.status_code == 200
    assert b"Step 3 of 3" in response.content, "Errors:" + str(response.context['form'].errors)

    #
    # Send data for third page
    #
    # TODO Do we have to really repeat all fields here?
    response = client.post(reverse('manager:topography-create',
                                   kwargs=dict(surface_id=surface.id)),
                           data={
                               'topography_create_wizard-current_step': '2',
                               '2-name': 'topo1',
                               '2-measurement_date': '2018-06-21',
                               '2-data_source': 0,
                               '2-description': description,
                               '2-size_x': '9000',
                               '2-size_y': '9000',
                               '2-size_unit': 'nm',
                               '2-height_scale': 0.3,
                               '2-height_unit': 'nm',
                               '2-detrend_mode': 'height',
                               '2-surface': surface.id,
                           }, follow=True)

    assert response.status_code == 200
    # assert reverse('manager:topography-detail', kwargs=dict(pk=1)) == response.url
    export_reponse_as_html(response)
    assert b'Details for Topography' in response.content

    surface = Surface.objects.get(name='surface1')
    topos = surface.topography_set.all()

    assert len(topos) == 1

    t = topos[0]

    assert t.measurement_date == datetime.date(2018,6,21)
    assert t.description == description
    assert "example3" in t.datafile.name

    #
    # should also appear in the list of topographies for the surface
    #
    response = client.get(reverse('manager:surface-detail', kwargs=dict(pk=surface.id)))
    assert bytes(description, 'utf-8') in response.content


@pytest.mark.django_db
def test_topography_list(client, two_topos, django_user_model):

    user = django_user_model.objects.get(username='testuser')

    assert client.login(username=user.username, password='abcd$1234')

    #
    # all topographies for 'testuser' should be listed
    #
    topos = Topography.objects.filter(user__username=user.username)
    response = client.get(reverse('manager:topography-list'))

    content = str(response.content)
    for t in topos:
        # currently 'listed' means: description in list, name in list
        assert t.description in content
        assert t.name in content

        # click on a row should lead to details, so URL must be included
        assert reverse('manager:topography-detail', kwargs=dict(pk=t.pk)) in content

        # TODO real test for click should be done with selenium

# TODO add test with predefined height conversion
# TODO add test with predefined physical size


@pytest.mark.django_db
def test_edit_topography(client, two_topos, django_user_model):

    new_name = "This is a better name"
    new_measurement_date = "2018-07-01"
    new_description = "New results available"
    #input_file_path = Topography.objects.get(pk=1).datafile.name

    username = 'testuser'
    password = 'abcd$1234'

    user = django_user_model.objects.get(username=username)

    assert client.login(username=username, password=password)

    #with open(str(input_file_path)) as fp:

    response = client.post(reverse('manager:topography-update', kwargs=dict(pk=1)),
                           data={
                            'name': new_name,
                            'measurement_date': new_measurement_date,
                            'description': new_description,
                            'user': user.id,
                            'size_x': 500,
                            'size_y': 1000,
                            'size_unit': 'nm',
                            'height_conv_scale': 0.1,
                            'height_conv_unit': 'nm',
                           })


    # assert 'form' not in response.context, "Still on form: {}".format(response.context['form'].errors)

    assert response.status_code == 302
    assert reverse('manager:topography-detail', kwargs=dict(pk=1)) == response.url

    # export_reponse_as_html(response) # TODO remove, only for debugging

    topos = Topography.objects.filter(user__username=username).order_by('pk')

    assert len(topos) == 2

    t = topos[0]

    assert t.measurement_date == datetime.date(2018, 7, 1)
    assert t.description == new_description
    assert "example4" in t.datafile.name

    #
    # should also appear in the list of topographies
    #
    response = client.get(reverse('manager:topography-list'))
    assert bytes(new_description, 'utf-8') in response.content
    assert bytes(new_name, 'utf-8') in response.content


@pytest.mark.django_db
def test_delete_topography(client, two_topos, django_user_model):

    # topography 1 is still in database
    assert Topography.objects.filter(pk=1).exists()

    username = 'testuser'
    password = 'abcd$1234'

    assert client.login(username=username, password=password)

    response = client.get(reverse('manager:topography-delete', kwargs=dict(pk=1)))

    # user should be asked if he/she is sure
    assert b'Are you sure' in response.content

    response = client.post(reverse('manager:topography-delete', kwargs=dict(pk=1)))

    assert reverse('manager:topography-list') == response.url

    # topography 1 is no more in database
    assert not Topography.objects.filter(pk=1).exists()

