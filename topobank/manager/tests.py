import pytest
from django.urls import resolve
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
def test_upload_topography(client):

    with open('fixtures/example4.txt') as fp:

        response = client.post(resolve('manager:topography-create'),
                               data={
                                    'measurement_date': datetime(2018,6,21),
                                    'datafile': fp,
                               })

    assert response.status_code == 200

    # TODO complete upload test












