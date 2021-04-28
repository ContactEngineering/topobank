"""
Tests for writing surface containers
"""
import zipfile
import yaml
import pytest
import tempfile
import os

from .utils import SurfaceFactory, Topography2DFactory, Topography1DFactory, TagModelFactory, UserFactory

from ..containers import write_surface_container


@pytest.mark.django_db
def test_surface_container():

    user = UserFactory()
    tag1 = TagModelFactory(name='apple')
    tag2 = TagModelFactory(name='banana')
    surface1 = SurfaceFactory(creator=user, tags=[tag1])
    surface2 = SurfaceFactory(creator=user)
    surface3 = SurfaceFactory(creator=user)
    surfaces = [surface1, surface2, surface3]
    topo1a = Topography1DFactory(surface=surface1)
    topo1b = Topography2DFactory(surface=surface1)

    topo2a = Topography2DFactory(surface=surface2, tags=[tag1, tag2])

    outfile = tempfile.NamedTemporaryFile(mode='wb', delete=False)
    write_surface_container(outfile, surfaces)
    outfile.close()

    # reopen and check contents
    with zipfile.ZipFile(outfile.name, mode='r') as zf:
        meta_file = zf.open('meta.yml')
        meta = yaml.load(meta_file)

        meta_surfaces = meta['surfaces']

        # check number of surfaces and topographies
        for surf_idx, surf in enumerate(surfaces):
            assert meta_surfaces[surf_idx]['name'] == surf.name
            assert len(meta_surfaces[surf_idx]['topographies']) == surf.topography_set.count()

        # check some tags
        assert meta_surfaces[0]['tags'] == ['apple']
        assert meta_surfaces[1]['topographies'][0]['tags'] == ['apple', 'banana']
    os.remove(outfile.name)


