import pytest
from django.urls import reverse
import datetime

from .models import Topography


#
# Test home page
#




#
# Model tests
#



#
# Upload tests
#
# Different formats are handled by PyCo
# and should be tested there
@pytest.mark.django_db
def test_upload_topography(client, django_user_model):

    username = 'testuser'
    password = 'abcd1234$'

    user = django_user_model.objects.create(username=username, password=password)

    assert user.username == username

    assert client.login(username=username, password=password)

    with open('topobank/manager/fixtures/example4.txt') as fp:

        response = client.post(reverse('manager:create'),
                               data={
                                    'measurement_date': datetime.datetime(2018,6,21),
                                    'datafile': fp,
                                    'description': "test",
                               }, follow=True)

    assert response.status_code == 200

    print(response.content)

    print([str(x) for x in Topography.objects.all()])

    topos = Topography.objects.filter(user__name=username)

    assert len(topos) == 1

    t = topos[0]

    assert t.measurement_date == datetime(2018,6,21)
    assert "example4.txt" in t.datafile.name
    assert t.description == "test"















