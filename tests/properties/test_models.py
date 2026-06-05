"""Tests for topobank.properties.models.Property helpers."""

import pytest

from topobank.properties.models import Property
from topobank.testing.factories import PropertyFactory, SurfaceFactory


@pytest.mark.django_db
def test_property_numerical_vs_categorical_flags():
    surface = SurfaceFactory()
    numerical = PropertyFactory.create(
        name="thickness", value=2.0, unit="mm", surface=surface
    )
    categorical = PropertyFactory.create(
        name="material", value="steel", surface=surface
    )

    assert numerical.is_numerical and not numerical.is_categorical
    assert categorical.is_categorical and not categorical.is_numerical


@pytest.mark.django_db
def test_property_str_and_to_dict():
    surface = SurfaceFactory()
    numerical = PropertyFactory.create(
        name="thickness", value=2.0, unit="mm", surface=surface
    )
    categorical = PropertyFactory.create(
        name="material", value="steel", surface=surface
    )

    assert str(numerical).startswith("thickness: 2.0")
    assert "mm" in str(numerical)
    assert str(categorical) == "material: steel"

    num_dict = numerical.to_dict()
    assert num_dict["name"] == "thickness"
    assert num_dict["value"] == 2.0
    assert num_dict["unit"] == "mm"

    cat_dict = categorical.to_dict()
    assert cat_dict == {"name": "material", "value": "steel"}


@pytest.mark.django_db
def test_property_deepcopy_to_other_surface():
    creator = SurfaceFactory().created_by
    source = SurfaceFactory(created_by=creator)
    target = SurfaceFactory(created_by=creator)
    prop = PropertyFactory.create(
        name="thickness", value=2.0, unit="mm", surface=source
    )

    prop.deepcopy(target)

    copied = Property.objects.get(surface=target, name="thickness")
    assert copied.pk != prop.pk
    assert copied.value_numerical == 2.0
    assert copied.permissions == target.permissions
