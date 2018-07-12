
import pytest
from django.shortcuts import reverse

from pathlib import Path
import datetime

from ..models import Topography
from .utils import two_topos

def export_reponse_as_html(response, fname='/tmp/response.html'):
    f = open(fname, mode='w')
    f.write(str(response.content).replace('\\n','\n'))
    f.close()

#
# Different formats are handled by PyCo
# and should be tested there
#
@pytest.mark.django_db
def test_upload_topography(client, django_user_model):

    # input_file_path = Path('../../../PyCo-web/PyCo_app/data/gain_control_uncd_dlc_4.004')
    input_file_path = Path('topobank/manager/fixtures/example4.txt') # TODO use standardized way to find files
    description = "test description"

    username = 'testuser'
    password = 'abcd$1234'


    user = django_user_model.objects.create_user(username=username, password=password)

    assert client.login(username=username, password=password)

    with open(str(input_file_path)) as fp:

        response = client.post(reverse('manager:create'),
                               data={
                                'name': 'surface1',
                                'measurement_date': '2018-06-21',
                                'datafile': fp,
                                'description': description,
                                'user': user.id,
                               })

    assert response.status_code == 302
    assert reverse('manager:detail', kwargs=dict(pk=1)) == response.url

    # export_reponse_as_html(response) # TODO remove, only for debugging

    topos = Topography.objects.filter(user__username=username)

    assert len(topos) == 1

    t = topos[0]

    assert t.measurement_date == datetime.date(2018,6,21)
    assert t.description == description
    assert "example4" in t.datafile.name

    #
    # should also appear in the list of topographies
    #
    response = client.get(reverse('manager:list'))
    assert bytes(description, 'utf-8') in response.content


@pytest.mark.django_db
def test_topography_list(client, two_topos, django_user_model):

    user = django_user_model.objects.get(username='testuser')

    assert client.login(username=user.username, password='abcd$1234')

    #
    # all topographies for 'testuser' should be listed
    #
    topos = Topography.objects.filter(user__username=user.username)
    response = client.get(reverse('manager:list'))

    content = str(response.content)
    for t in topos:
        # currently 'listed' means: filename and description in list
        assert t.datafile.name in content
        assert t.description in content

        # click on a row should lead to details, so URL must be included
        assert reverse('manager:detail', kwargs=dict(pk=t.pk)) in content

        # TODO real test for click should be done with selenium


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

    response = client.post(reverse('manager:update', kwargs=dict(pk=1)),
                           data={
                            'name': new_name,
                            'measurement_date': new_measurement_date,
                            'description': new_description,
                            'user': user.id,
                           })


    # assert 'form' not in response.context, "Still on form: {}".format(response.context['form'].errors)

    assert response.status_code == 302
    assert reverse('manager:detail', kwargs=dict(pk=1)) == response.url

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
    response = client.get(reverse('manager:list'))
    assert bytes(new_description, 'utf-8') in response.content


