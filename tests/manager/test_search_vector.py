"""
Tests for the full-text search index on `Surface`.

`Surface.build_search_document` assembles the searchable text from a dataset and
its measurements, and the signal handlers in `manager.signals` keep
`Surface.search_vector` current as either changes. These tests pin down what ends
up in the index and, just as importantly, which saves do *not* trigger a
re-index.
"""

import pytest
from django.contrib.postgres.search import SearchQuery

from topobank.manager.models import Surface, Measurement
from topobank.testing.factories import (
    SurfaceFactory,
    TagFactory,
    Topography2DFactory,
)


def search(term):
    return Surface.objects.filter(search_vector=SearchQuery(term, config="english"))


@pytest.mark.django_db
def test_measurement_name_is_indexed():
    surface = SurfaceFactory(name="A dataset")
    Topography2DFactory(surface=surface, name="distinctive-measurement.txt")

    surface.refresh_from_db()
    assert "distinctive" in str(surface.search_vector)
    assert surface in search("distinctive")


@pytest.mark.django_db
def test_measurement_description_is_indexed():
    surface = SurfaceFactory()
    Topography2DFactory(surface=surface, description="sputtered aluminium")

    assert surface in search("sputtered")


@pytest.mark.django_db
def test_renaming_a_measurement_reindexes_its_dataset():
    surface = SurfaceFactory()
    # Note: the index uses the 'english' configuration, so the terms must not be
    # stop words ("before"/"after" would be stripped).
    topography = Topography2DFactory(surface=surface, name="aluminium.txt")
    assert surface in search("aluminium")

    topography.name = "titanium.txt"
    topography.save(update_fields=["name"])

    assert surface in search("titanium")
    assert surface not in search("aluminium")


@pytest.mark.django_db
def test_measurement_tags_are_indexed():
    surface = SurfaceFactory()
    topography = Topography2DFactory(surface=surface)
    tag = TagFactory(name="anodized")

    topography.tags = [tag]
    topography.save()

    assert surface in search("anodized")


@pytest.mark.django_db
def test_deleting_a_measurement_reindexes_its_dataset():
    surface = SurfaceFactory()
    topography = Topography2DFactory(surface=surface, name="doomed.txt")
    assert surface in search("doomed")

    topography.delete()

    assert surface not in search("doomed")


@pytest.mark.django_db
def test_a_save_that_touches_no_searchable_field_does_not_reindex(mocker):
    """
    Only `name`, `description` and `created_by` contribute to the document.

    Worth pinning down: physical metadata is rewritten on every inspection, and
    re-indexing the whole dataset on each of those would be pure overhead. The
    assertion is on `update_search_vector` rather than on the stored vector,
    because recomputing the document would leave the vector unchanged anyway --
    that is exactly the wasted work being guarded against.
    """
    surface = SurfaceFactory()
    topography = Topography2DFactory(surface=surface, name="stable.txt")
    reindex = mocker.patch.object(Surface, "update_search_vector")

    topography.detrend_mode = "height"
    topography.save(update_fields=["detrend_mode"])

    reindex.assert_not_called()
    assert Measurement.objects.get(pk=topography.pk).detrend_mode == "height"


@pytest.mark.django_db
def test_a_save_that_touches_a_searchable_field_reindexes(mocker):
    """The counterpart to the above: the guard must not swallow a real change."""
    surface = SurfaceFactory()
    topography = Topography2DFactory(surface=surface, name="stable.txt")
    reindex = mocker.patch.object(Surface, "update_search_vector")

    topography.name = "renamed.txt"
    topography.save(update_fields=["name"])

    reindex.assert_called()
