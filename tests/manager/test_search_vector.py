"""
The full-text search index still covers measurements after the rename.

`Surface.build_search_document` walks its measurements, and signal handlers keep
the vector current, so both had to follow the renamed relation.
"""

import pytest
from django.contrib.postgres.search import SearchQuery

from topobank.manager.models import Measurement, Surface
from topobank.testing.factories import (
    SurfaceFactory,
    TagFactory,
    TopographyMapFactory,
)


def search(term):
    return Surface.objects.filter(search_vector=SearchQuery(term, config="english"))


@pytest.mark.django_db
def test_measurement_name_is_indexed():
    surface = SurfaceFactory(name="A dataset")
    TopographyMapFactory(surface=surface, name="distinctive-measurement.txt")

    surface.refresh_from_db()
    assert "distinctive" in str(surface.search_vector)
    assert surface in search("distinctive")


@pytest.mark.django_db
def test_measurement_description_is_indexed():
    surface = SurfaceFactory()
    TopographyMapFactory(surface=surface, description="sputtered aluminium")

    assert surface in search("sputtered")


@pytest.mark.django_db
def test_renaming_a_measurement_reindexes_its_dataset():
    surface = SurfaceFactory()
    # Note: the index uses the 'english' configuration, so the terms must not be
    # stop words ("before"/"after" would be stripped).
    measurement = TopographyMapFactory(surface=surface, name="aluminium.txt")
    assert surface in search("aluminium")

    measurement.name = "titanium.txt"
    measurement.save(update_fields=["name"])

    assert surface in search("titanium")
    assert surface not in search("aluminium")


@pytest.mark.django_db
def test_measurement_tags_are_indexed():
    surface = SurfaceFactory()
    measurement = TopographyMapFactory(surface=surface)
    tag = TagFactory(name="anodized")

    measurement.tags = [tag]
    measurement.save()

    assert surface in search("anodized")


@pytest.mark.django_db
def test_deleting_a_measurement_reindexes_its_dataset():
    surface = SurfaceFactory()
    measurement = TopographyMapFactory(surface=surface, name="doomed.txt")
    assert surface in search("doomed")

    measurement.delete()

    assert surface not in search("doomed")


@pytest.mark.django_db
def test_metadata_only_save_does_not_need_reindexing():
    """
    Metadata is not part of the search document.

    Worth pinning down: `metadata` is written on every inspection, and re-indexing
    on each of those would be pure overhead.
    """
    surface = SurfaceFactory()
    measurement = TopographyMapFactory(surface=surface, name="stable.txt")
    surface.refresh_from_db()
    before = surface.search_vector

    measurement.update_metadata(detrend_mode="height")

    surface.refresh_from_db()
    assert surface.search_vector == before
    assert Measurement.objects.get(pk=measurement.pk).meta.detrend_mode == "height"
