import pytest

from rest_framework.reverse import reverse


@pytest.mark.django_db
def test_categorical_value_cannot_have_units(api_client, one_line_scan):
    # `api_client` is a fixture from django-rest-framework
    # `one_line_scan` is a fixture from topobank.manager.tests.utils that
    # creates a user and a surface with a topography
    username = 'testuser'
    password = 'abcd$1234'

    surface_id = one_line_scan.surface.id

    assert api_client.login(username=username, password=password)

    # create a categorical property
    response = api_client.post(reverse('manager:property-api-list'),
                               data=dict(name="color", value="brown"))
    assert response.status_code == 201

    # attempt creating a categorical property with a unit
    response = api_client.post(reverse('manager:property-api-list'),
                               data=dict(name="color", value="brown", unit="km"))
    assert response.status_code == 400
