"""
Testing management commands for manager app.
"""

import tempfile

import pytest
from django.core.management import call_command
from django.shortcuts import reverse

from topobank.manager.models import Surface
from topobank.testing.factories import (
    SurfaceFactory,
    Topography1DFactory,
    Topography2DFactory,
    UserFactory,
)


@pytest.mark.django_db
def test_import_downloaded_surface_archive(client, handle_usage_statistics):
    username = 'test_user'
    surface_name = "Test Surface for Import"
    surface_category = 'dum'
    user = UserFactory(username=username)
    surface = SurfaceFactory(created_by=user, name=surface_name, category=surface_category)
    Topography2DFactory(surface=surface, name='2D Measurement', size_x=10, size_y=10, unit='mm')
    Topography1DFactory(surface=surface, name='1D Measurement', size_x=9, unit='µm')

    client.force_login(user)

    download_url = reverse('manager:surface-download', kwargs=dict(surface_ids=surface.id))
    response = client.get(download_url)

    # write downloaded data to temporary file and open
    with tempfile.NamedTemporaryFile(mode='wb') as zip_archive:
        zip_archive.write(response.content)
        zip_archive.seek(0)

        # reimport the surface
        call_command('import_datasets', username, zip_archive.name)

    surface_copy = Surface.objects.get(description__icontains='imported from file')

    #
    # Check surface
    #
    assert surface_copy.name == surface.name
    assert surface_copy.category == surface.category
    assert surface.description in surface_copy.description
    assert surface_copy.tags == surface.tags

    #
    # Check imported topographies
    #
    assert surface_copy.num_topographies() == surface.num_topographies()

    for tc, t in zip(surface_copy.topography_set.order_by('name'), surface.topography_set.order_by('name')):

        #
        # Compare individual topographies
        #
        for attrname in ['name', 'description', 'size_x', 'size_y', 'height_scale',
                         'measurement_date', 'unit', 'created_by', 'data_source', 'tags']:
            assert getattr(tc, attrname) == getattr(t, attrname)


@pytest.mark.django_db
def test_refresh_cache(mocker):
    Topography2DFactory()
    refresh_cache_mock = mocker.patch('topobank.manager.models.Topography.refresh_cache')

    call_command('refresh_cache', background=False)

    assert refresh_cache_mock.called
