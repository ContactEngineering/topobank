"""
Testing management commands for manager app.
"""
from django.core.management import call_command

import pytest
import datetime
from pathlib import Path

from topobank.manager.tests.utils import Surface, UserFactory, FIXTURE_DIR


@pytest.mark.django_db
def test_import_surface():

    username = 'test_user'
    surface_name = "Test Surface for Import"
    surface_category = 'dum'
    user = UserFactory(username=username)
    input_file_path = Path(FIXTURE_DIR + '/surface_for_import.zip')

    assert Surface.objects.count() == 0

    # generate the surface
    call_command('import_surface', username, input_file_path,
                 '--name', surface_name, '--category', surface_category)

    assert Surface.objects.count() == 1

    #
    # Check surface
    #
    surface = Surface.objects.get(name=surface_name)
    assert surface.category == surface_category
    assert surface.num_topographies() == 2
    assert "Imported from file" in surface.description

    #
    # Check imported topographies
    #
    t0, t1 = surface.topography_set.order_by('name')

    assert t0.name == 'topo_1D.txt'
    assert t0.description == "1D Example"
    assert t0.size_x == 10.
    assert t0.size_y is None
    assert t0.height_scale == 2.0
    assert t0.measurement_date == datetime.date(2021, 3, 23)
    assert t0.unit == "nm"
    assert t0.creator == user
    assert t0.data_source == 0

    assert t1.name == 'topo_2D.txt'
    assert t1.description == "2D Example"
    assert t1.size_x == 10.
    assert t1.size_y == 10.
    assert t1.height_scale == 1.0
    assert t1.measurement_date == datetime.date(2021, 3, 24)
    assert t1.unit == "\xB5m"
    assert t1.creator == user
    assert t1.data_source == 0







