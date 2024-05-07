import numpy as np
import pytest
from django.core.exceptions import ValidationError
from rest_framework.reverse import reverse

from topobank.manager.models import Property


@pytest.mark.django_db(transaction=True)
def test_wrong_unit(one_line_scan):
    prop = Property(name="test", value=1.0, unit="csc")
    with pytest.raises(ValidationError):
        prop.save()


@pytest.mark.django_db
def test_categorical_value_cannot_have_units(api_client, one_line_scan):
    # `api_client` is a fixture from django-rest-framework
    # `one_line_scan` is a fixture from topobank.manager.tests.utils that
    # creates a user and a surface with a topography
    username = 'testuser'
    password = 'abcd$1234'

    surface_id = one_line_scan.surface.id
    surface_api_url = reverse('manager:surface-api-detail', [surface_id])

    assert api_client.login(username=username, password=password)

    # create a categorical property
    response = api_client.post(reverse('manager:property-api-list'),
                               data=dict(name="color", value="brown", surface=surface_api_url))
    assert response.status_code == 201

    # attempt creating a categorical property with a unit
    response = api_client.post(reverse('manager:property-api-list'),
                               data=dict(name="color", value="brown", unit="km", surface=surface_api_url))
    assert response.status_code == 400

    # attempt creating a categorical property with a dimensionless unit
    response = api_client.post(reverse('manager:property-api-list'),
                               data=dict(name="color", value="brown", unit="", surface=surface_api_url))
    assert response.status_code == 400


@pytest.mark.django_db
def test_numerical_value_must_have_units(api_client, one_line_scan, handle_usage_statistics):
    # `api_client` is a fixture from django-rest-framework
    # `one_line_scan` is a fixture from topobank.manager.tests.utils that
    # creates a user and a surface with a topography
    username = 'testuser'
    password = 'abcd$1234'

    assert api_client.login(username=username, password=password)

    surface_id = one_line_scan.surface.id
    surface_api_url = reverse('manager:surface-api-detail', [surface_id])

    # create a numerical property
    response = api_client.post(reverse('manager:property-api-list'),
                               data=dict(name="height", value=42, unit="meter", surface=surface_api_url))
    assert response.status_code == 201

    # create a numerical property with float value
    response = api_client.post(reverse('manager:property-api-list'),
                               data=dict(name="area", value=1.99, unit="m^2", surface=surface_api_url))
    assert response.status_code == 201

    # attempt creating a numerical property with a dimensionless unit
    response = api_client.post(reverse('manager:property-api-list'),
                               data=dict(name="level", value=9001, unit="", surface=surface_api_url))
    assert response.status_code == 201

    # attempt creating a numerical property with no unit
    response = api_client.post(reverse('manager:property-api-list'),
                               data=dict(name="dings", value=1337, surface=surface_api_url))
    assert response.status_code == 400

    # create a numerical property with wrong unit
    response = api_client.post(reverse('manager:property-api-list'),
                               data=dict(name="stupid-unit", value=1.99, unit="m2", surface=surface_api_url))
    assert response.status_code == 400


@pytest.mark.django_db
def test_properties(user_three_topographies_three_surfaces_three_tags):
    user, (topo1a, topo1b, topo2a), (surface1, surface2, surface3), (tag1, tag2, tag3) \
        = user_three_topographies_three_surfaces_three_tags

    surface1.properties.create(name="height", value=42, unit="m")
    surface2.properties.create(name="height", value=12, unit="m")
    surface2.properties.create(name="category", value='abc')
    surface3.properties.create(name="category", value='def')

    tag3.surface_set.add(surface2)

    tag1_values, tag1_infos = tag1.get_properties()
    assert tag1_values == {'height': [42]}
    tag2_values, tag2_infos = tag2.get_properties()
    assert tag2_values == {'height': [12], 'category': ['abc']}
    tag3_values, tag3_infos = tag3.get_properties()
    assert tag3_values == {'height': [12, np.nan], 'category': ['abc', 'def']}
