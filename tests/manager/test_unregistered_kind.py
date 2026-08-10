"""
Behavior when a measurement's kind is not registered.

This is what a user sees after a plugin that provided a kind of measurement is
uninstalled, and it is the case that decides whether the pluggable design is safe
to deploy: the record must stay usable as a record even when nothing can interpret
its data.
"""

import pytest

from topobank.manager.models import Measurement
from topobank.measurements.registry import (
    MeasurementNotInspectedError,
    UnknownMeasurementKindError,
)
from topobank.testing.factories import (
    SurfaceFactory,
    TopographyMapFactory,
)

UNKNOWN_KIND = "xps-spectrum"


@pytest.fixture
def orphaned(db):
    """A measurement whose kind no longer has a registered measurement type."""
    measurement = TopographyMapFactory()
    # Written straight to the database: the model would refuse to validate
    # metadata for a kind it cannot resolve.
    Measurement.objects.filter(pk=measurement.pk).update(
        kind=UNKNOWN_KIND, metadata={"kind": UNKNOWN_KIND, "binding_energy": 284.8}
    )
    return Measurement.objects.get(pk=measurement.pk)


@pytest.mark.django_db
class TestRemainsUsableAsARecord:
    """Listing, downloading and deleting must not depend on the kind."""

    def test_is_listed(self, orphaned):
        assert orphaned in Measurement.objects.all()
        assert Measurement.objects.filter(kind=UNKNOWN_KIND).count() == 1

    def test_name_and_labels_work(self, orphaned):
        assert orphaned.label == orphaned.name
        assert str(orphaned) == f"Measurement '{orphaned.name}'"

    def test_datafile_is_still_reachable(self, orphaned):
        """The raw file is what makes the record worth keeping."""
        assert orphaned.datafile.exists()
        assert len(orphaned.datafile.read()) > 0

    def test_unrelated_save_still_works(self, orphaned):
        """
        A save that does not touch metadata must not try to interpret it.

        Otherwise routine bulk operations would start failing across the site
        because of a single uninstalled plugin.
        """
        orphaned.description = "still editable"
        orphaned.save(update_fields=["description"])
        assert Measurement.objects.get(pk=orphaned.pk).description == "still editable"

    def test_can_be_soft_and_hard_deleted(self, orphaned):
        orphaned.lazy_delete()
        assert orphaned.deletion_time is not None
        orphaned.delete()
        assert not Measurement.all_objects.filter(pk=orphaned.pk).exists()

    def test_is_excluded_from_surface_containers(self, db):
        """
        A container yields SurfaceTopography objects, so it can only contain
        measurements whose type produces them.
        """
        surface = SurfaceFactory()
        readable = TopographyMapFactory(surface=surface)
        unreadable = TopographyMapFactory(surface=surface, name="orphan")
        # `kind` and `metadata["kind"]` are kept in step by a database
        # constraint, so both have to move together.
        Measurement.objects.filter(pk=unreadable.pk).update(
            kind=UNKNOWN_KIND, metadata={"kind": UNKNOWN_KIND}
        )

        container = surface.lazy_read()
        assert len(container) == 1
        assert container[0] is not None
        assert readable.kind == "topography-map"


@pytest.mark.django_db
class TestDataAccessIsBlocked:
    def test_get_type_raises(self, orphaned):
        with pytest.raises(UnknownMeasurementKindError) as excinfo:
            orphaned.get_type()
        assert UNKNOWN_KIND in str(excinfo.value)

    def test_read_raises(self, orphaned):
        with pytest.raises(UnknownMeasurementKindError):
            orphaned.read()

    def test_metadata_cannot_be_interpreted(self, orphaned):
        with pytest.raises(UnknownMeasurementKindError):
            orphaned.meta

    def test_metadata_cannot_be_edited(self, orphaned):
        """There is no schema to validate against, so editing is refused."""
        with pytest.raises(UnknownMeasurementKindError):
            orphaned.update_metadata(binding_energy=100.0)

    def test_metadata_is_not_reported_complete(self, orphaned):
        """Used to decide whether to generate derived files; must not raise."""
        assert orphaned.is_metadata_complete is False

    def test_reinspection_repairs_the_record(self, orphaned):
        """
        The kind comes from the data file, so re-inspecting repairs the record.

        This is the recovery path when a kind was written by a plugin that is gone
        but the underlying data is something the core understands. Metadata that
        belonged to the old kind is dropped, since the new schema has no such
        fields.
        """
        orphaned.refresh_cache()

        assert orphaned.kind == "topography-map"
        # Parseable again...
        assert orphaned.meta.kind == "topography-map"
        # ...and the foreign metadata is gone rather than lingering.
        assert "binding_energy" not in orphaned.metadata


@pytest.mark.django_db
class TestNotInspectedYet:
    """An uninspected measurement has no kind either, but for a different reason."""

    def test_get_type_says_it_is_not_inspected(self, db):
        surface = SurfaceFactory()
        measurement = Measurement(
            surface=surface,
            created_by=surface.created_by,
            permissions=surface.permissions,
            name="not-inspected.txt",
        )
        measurement.save()

        assert measurement.kind == ""
        with pytest.raises(MeasurementNotInspectedError):
            measurement.get_type()
        assert measurement.is_metadata_complete is False
