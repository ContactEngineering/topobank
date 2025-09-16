"""
Tests for writing surface containers
"""

import os
import tempfile
import zipfile

import pytest
import yaml
from notifications.models import Notification

import topobank
from topobank.manager.export_zip import export_container_zip
from topobank.manager.models import Surface, Topography
from topobank.manager.tasks import import_container_from_url
from topobank.testing.factories import (
    PropertyFactory,
    SurfaceFactory,
    TagFactory,
    Topography1DFactory,
    Topography2DFactory,
    UserFactory,
)


@pytest.mark.django_db
def test_surface_container(example_authors):
    instrument_name = "My nice profilometer"
    instrument_type = "contact-based"
    instrument_params = {
        "tip_radius": {
            "value": 10,
            "unit": "µm",
        }
    }
    has_undefined_data = False
    fill_undefined_data_mode = Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING

    user = UserFactory()
    tag1 = TagFactory(name="apple")
    tag2 = TagFactory(name="banana")
    surface1 = SurfaceFactory(creator=user, tags=[tag1])
    surface2 = SurfaceFactory(creator=user)
    surface3 = SurfaceFactory(creator=user, description="Nice results")

    PropertyFactory.create(name="categorical", value="abc", surface=surface2)
    PropertyFactory.create(name="numerical", value=1, unit="m", surface=surface2)

    topo1a = Topography1DFactory(surface=surface1)
    topo1b = Topography2DFactory(
        surface=surface1, datafile__filename="example4.txt", height_scale_editable=False
    )
    # for topo1b we use a datafile which has an height_scale_factor defined - this is needed in order
    # to test that this factor is NOT exported to meta.yaml -
    # for the initialisation syntax (datafile__filename) here see:
    # https://factoryboy.readthedocs.io/en/stable/orms.html

    topo2a = Topography2DFactory(
        surface=surface2,
        tags=[tag1, tag2],
        description="Nice measurement",
        size_x=10,
        size_y=5,
        instrument_name=instrument_name,
        instrument_type=instrument_type,
        instrument_parameters=instrument_params,
        has_undefined_data=has_undefined_data,
        fill_undefined_data_mode=fill_undefined_data_mode,
    )

    # surface 3 is empty
    surfaces = [surface1, surface2, surface3]

    # make sure all squeezed files have been generated
    for t in [topo1a, topo1b, topo2a]:
        t.make_squeezed(save=True)

    #
    # Create container file
    #
    outfile = tempfile.NamedTemporaryFile(mode="wb", delete=False)
    export_container_zip(outfile, surfaces)
    outfile.close()

    # reopen and check contents
    with zipfile.ZipFile(outfile.name, mode="r") as zf:
        meta_file = zf.open("meta.yml")
        meta = yaml.safe_load(meta_file)

        meta_surfaces = meta["surfaces"]

        # check number of surfaces and topographies
        for surf_idx, surf in enumerate(surfaces):
            assert meta_surfaces[surf_idx]["name"] == surf.name
            assert meta_surfaces[surf_idx]["category"] == surf.category
            assert meta_surfaces[surf_idx]["description"] == surf.description
            assert meta_surfaces[surf_idx]["creator"]["name"] == surf.creator.name
            assert meta_surfaces[surf_idx]["creator"]["orcid"] == surf.creator.orcid_id
            assert (
                len(meta_surfaces[surf_idx]["topographies"])
                == surf.topography_set.count()
            )

        # check some tags
        assert meta_surfaces[0]["tags"] == ["apple"]
        assert meta_surfaces[1]["topographies"][0]["tags"] == ["apple", "banana"]

        # all data files should be included
        for surf_descr in meta_surfaces:
            for topo_descr in surf_descr["topographies"]:
                datafile_name = topo_descr["datafile"]["original"]
                assert datafile_name in zf.namelist()
                squeezed_datafile_name = topo_descr["datafile"]["squeezed-netcdf"]
                assert squeezed_datafile_name in zf.namelist()

        # check version information
        assert meta["versions"]["topobank"] == topobank.__version__
        assert "creation_time" in meta

        # check publication fields
        assert not meta_surfaces[0]["is_published"]
        assert not meta_surfaces[1]["is_published"]
        assert not meta_surfaces[2]["is_published"]

        # topo1a should have an height_scale_factor in meta data because
        # this information is not included in the data file
        topo1a_meta = meta_surfaces[0]["topographies"][0]
        assert "height_scale" in topo1a_meta

        #
        # topo1b should have no height_scale_factor included
        # because it's already applied on import, see GH 718
        #
        topo1b_meta = meta_surfaces[0]["topographies"][1]
        assert topo1b_meta["name"] == topo1b.name
        assert "height_scale" not in topo1b_meta

        assert "fill_undefined_data_mode" in topo1a_meta
        assert "fill_undefined_data_mode" in topo1b_meta
        assert "has_undefined_data" in topo1a_meta
        assert "has_undefined_data" in topo1b_meta

        # check properties
        assert "properties" in meta_surfaces[1]
        assert len(meta_surfaces[1]["properties"]) == 2
        assert meta_surfaces[1]["properties"][0]["name"] == "categorical"
        assert meta_surfaces[1]["properties"][0]["value"] == "abc"
        assert meta_surfaces[1]["properties"][1]["name"] == "numerical"
        assert meta_surfaces[1]["properties"][1]["value"] == 1
        assert meta_surfaces[1]["properties"][1]["unit"] == "m"

    os.remove(outfile.name)


@pytest.mark.django_db
def test_import():
    user = UserFactory(username="testuser1", password="abcd$1234")
    surface_id = import_container_from_url(
        user, "https://contact.engineering/go/867nv"
    ).id
    surface = Surface.objects.get(id=surface_id)
    assert surface.name == "Self-affine synthetic surface"
    assert surface.topography_set.count() == 3
    assert surface.description.startswith(
        "This surface contains virtual measurements taken"
    )
    assert (
        Notification.objects.filter(
            recipient=user,
            verb="imported",
            description__startswith="Successfully import digital surface twin",
        ).count()
        == 1
    )
