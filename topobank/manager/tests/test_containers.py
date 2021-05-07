"""
Tests for writing surface containers
"""
import zipfile
import yaml
import pytest
import tempfile
import os

from django.conf import settings

from .utils import SurfaceFactory, Topography2DFactory, Topography1DFactory, TagModelFactory, UserFactory

from ..containers import write_surface_container


@pytest.mark.django_db
def test_surface_container():

    user = UserFactory()
    tag1 = TagModelFactory(name='apple')
    tag2 = TagModelFactory(name='banana')
    surface1 = SurfaceFactory(creator=user, tags=[tag1])
    surface2 = SurfaceFactory(creator=user)
    surface3 = SurfaceFactory(creator=user, description='Nice results')

    topo1a = Topography1DFactory(surface=surface1)
    topo1b = Topography2DFactory(surface=surface1)
    topo2a = Topography2DFactory(surface=surface2,
                                 tags=[tag1, tag2],
                                 description='Nice measurement',
                                 size_x=10, size_y=5)
    # surface 3 is empty

    # surface 2 is published
    publication = surface2.publish('cc0-1.0', 'Test User')
    surface4 = publication.surface

    surfaces = [surface1, surface2, surface3, surface4]

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
            assert meta_surfaces[surf_idx]['category'] == surf.category
            assert meta_surfaces[surf_idx]['description'] == surf.description
            assert meta_surfaces[surf_idx]['creator']['name'] == surf.creator.name
            assert meta_surfaces[surf_idx]['creator']['orcid'] == surf.creator.orcid_id
            assert len(meta_surfaces[surf_idx]['topographies']) == surf.topography_set.count()

        # check some tags
        assert meta_surfaces[0]['tags'] == ['apple']
        assert meta_surfaces[1]['topographies'][0]['tags'] == ['apple', 'banana']

        # all data files should be included
        for surf_descr in meta_surfaces:
            for topo_descr in surf_descr['topographies']:
                datafile_name = topo_descr['datafile']['original']
                assert datafile_name in zf.namelist()

        # check version information
        assert meta['versions']['topobank'] == settings.TOPOBANK_VERSION
        assert 'creation_time' in meta

        # check publication fields
        assert not meta_surfaces[0]['is_published']
        assert not meta_surfaces[1]['is_published']
        assert not meta_surfaces[2]['is_published']
        assert meta_surfaces[3]['is_published']
        meta_surface4 = meta_surfaces[3]
        meta_surface_4_pub = meta_surface4['publication']
        assert meta_surface_4_pub['authors'] == "Test User"
        assert meta_surface_4_pub['license'] == settings.CC_LICENSE_INFOS['cc0-1.0']['option_name']
        assert meta_surface_4_pub['version'] == 1

        # check some topography fields
        topo_meta = meta_surface4['topographies'][0]
        assert topo_meta['tags'] == ['apple', 'banana']
        for field in ['is_periodic', 'description', 'detrend_mode',
                      'data_source', 'height_scale', 'measurement_date', 'name', 'unit']:
            assert topo_meta[field] == getattr(topo2a, field)
        assert topo_meta['size'] == (topo2a.size_x, topo2a.size_y)

    os.remove(outfile.name)


