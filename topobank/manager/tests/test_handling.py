from django.shortcuts import reverse
from pathlib import Path
import datetime
import pytest

from ..models import Topography

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

    # input_file_path = Path('../PyCo-web/PyCo_app/data/gain_control_uncd_dlc_4.004')
    input_file_path = Path('../fixtures/example4.txt') # TODO use standardized way to find files
    description = "test description"

    username = 'testuser'
    password = 'abcd1234$'


    user = django_user_model.objects.create_user(username=username, password=password)

    assert client.login(username=username, password=password)

    with open(str(input_file_path)) as fp:

        response = client.post(reverse('manager:create'),
                               data={
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



