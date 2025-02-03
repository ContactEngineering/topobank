import numpy as np
import pytest
from django.core.exceptions import ValidationError
from rest_framework.reverse import reverse

from topobank.properties.models import Property
from topobank.testing.factories import UserFactory


@pytest.mark.django_db
def test_wrong_unit(one_line_scan):
    prop = Property(name="test", value=1.0, unit="csc")
    with pytest.raises(ValidationError):
        prop.save()


@pytest.mark.django_db
def test_categorical_value_cannot_have_units(api_client, one_line_scan):
    # `api_client` is a fixture from django-rest-framework
    # `one_line_scan` is a fixture from topobank.manager.supplib.utils that
    # creates a user and a surface with a topography
    username = "testuser"
    password = "abcd$1234"

    surface_id = one_line_scan.surface.id
    surface_api_url = reverse("manager:surface-api-detail", [surface_id])

    # creating a categorical property without logging in should fail
    response = api_client.patch(
        surface_api_url,
        data=dict(properties=dict(color=dict(value="brown"))),
    )
    assert response.status_code == 403

    assert api_client.login(username=username, password=password)

    # create a categorical property
    response = api_client.patch(
        surface_api_url,
        data=dict(properties=dict(color=dict(value="brown"))),
    )
    assert response.status_code == 200

    # attempt creating a categorical property with a unit
    response = api_client.patch(
        surface_api_url,
        data=dict(properties=dict(color=dict(value="brown", unit="km"))),
    )
    assert response.status_code == 400

    # attempt creating a categorical property with a dimensionless unit
    response = api_client.patch(
        surface_api_url,
        data=dict(properties=dict(color=dict(value="brown", unit=""))),
    )
    assert response.status_code == 400

    # Create another user and login
    user2 = UserFactory()
    api_client.force_login(user2)

    # Creating a categorical property should fail because user2 has no access to the
    # dataset
    response = api_client.patch(
        surface_api_url,
        data=dict(properties=dict(smell=dict(value="flowery"))),
    )
    assert response.status_code == 404

    # Share surface
    one_line_scan.surface.grant_permission(user2, "edit")

    # Creating a categorical property should succeed now
    response = api_client.patch(
        surface_api_url,
        data=dict(properties=dict(smell=dict(value="flowery"))),
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_numerical_value_must_have_units(
    api_client, one_line_scan, handle_usage_statistics
):
    # `api_client` is a fixture from django-rest-framework
    # `one_line_scan` is a fixture from topobank.manager.supplib.utils that
    # creates a user and a surface with a topography
    username = "testuser"
    password = "abcd$1234"

    assert api_client.login(username=username, password=password)

    surface_id = one_line_scan.surface.id
    surface_api_url = reverse("manager:surface-api-detail", [surface_id])

    # create a numerical property
    response = api_client.patch(
        surface_api_url,
        data=dict(properties=dict(height=dict(value=42, unit="meter"))),
    )
    assert response.status_code == 200

    # create a numerical property with float value
    response = api_client.patch(
        surface_api_url,
        data=dict(properties=dict(area=dict(value=1.99, unit="m^2"))),
    )
    assert response.status_code == 200

    # attempt creating a numerical property with a dimensionless unit
    response = api_client.patch(
        surface_api_url,
        data=dict(properties=dict(level=dict(value=9001, unit=""))),
    )
    assert response.status_code == 200

    # attempt creating a numerical property with no unit
    response = api_client.patch(
        surface_api_url,
        data=dict(properties=dict(dings=dict(value=1337))),
    )
    assert response.status_code == 400

    # create a numerical property with wrong unit
    response = api_client.patch(
        surface_api_url,
        data=dict(properties=dict({"stupid-unit": dict(value=1.99, unit="m2")})),
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_tag_properties(user_three_topographies_three_surfaces_three_tags):
    (
        user,
        (topo1a, topo1b, topo2a),
        (surface1, surface2, surface3),
        (tag1, tag2, tag3),
    ) = user_three_topographies_three_surfaces_three_tags

    surface1.properties.create(name="height", value=42, unit="m")
    surface2.properties.create(name="height", value=12, unit="m")
    surface2.properties.create(name="category", value="abc")
    surface3.properties.create(name="category", value="def")

    tag3.surface_set.add(surface2)

    tag1_values, tag1_infos = tag1.get_properties()
    assert tag1_values == {"height": [42]}
    tag2_values, tag2_infos = tag2.get_properties()
    assert tag2_values == {"height": [12], "category": ["abc"]}
    tag3_values, tag3_infos = tag3.get_properties()
    assert tag3_values == {"height": [12, np.nan], "category": ["abc", "def"]}


@pytest.mark.django_db
def test_tag_property_routes(
    api_client, user_three_topographies_three_surfaces_three_tags
):
    (
        user,
        (topo1a, topo1b, topo2a),
        (surface1, surface2, surface3),
        (tag1, tag2, tag3),
    ) = user_three_topographies_three_surfaces_three_tags

    surface1.properties.create(name="height", value=42, unit="m")
    surface2.properties.create(name="height", value=12, unit="m")
    surface2.properties.create(name="category", value="abc")
    surface3.properties.create(name="category", value="def")

    tag3.surface_set.add(surface2)

    api_client.force_login(user)

    response = api_client.get(reverse("manager:numerical-properties", [tag1.name]))
    assert response.data == {"names": ["height"]}
    response = api_client.get(reverse("manager:categorical-properties", [tag1.name]))
    assert response.data == {"names": []}
    response = api_client.get(reverse("manager:numerical-properties", [tag2.name]))
    assert response.data == {"names": ["height"]}
    response = api_client.get(reverse("manager:categorical-properties", [tag2.name]))
    assert response.data == {"names": ["category"]}
    response = api_client.get(reverse("manager:numerical-properties", [tag3.name]))
    assert response.data == {"names": ["height"]}
    response = api_client.get(reverse("manager:categorical-properties", [tag3.name]))
    assert response.data == {"names": ["category"]}
    response = api_client.get(reverse("manager:numerical-properties", ["nonexistent"]))
    assert "detail" in response.data
    assert response.status_code == 404
    response = api_client.get(reverse("manager:categorical-properties", ["nonexistent"]))
    assert "detail" in response.data
    assert response.status_code == 404
