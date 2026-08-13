"""
Backfill `Measurement.kind` for measurements that have already been inspected.

The kind is normally derived from the selected channel while the data file is
inspected, but reopening every stored file here would be far too slow. The values
inspection already wrote to the typed columns are enough to reconstruct it:

* ``resolution_y`` is set only for two-dimensional data, so a non-null value means
  the record is a topography map.
* ``is_periodic_editable`` is cleared only for non-uniform data (periodicity is
  meaningless there), so among the one-dimensional records it separates the
  non-uniform line scans from the uniform ones.

``resolution_x`` is written on every inspection, so a null there means the file has
never been inspected. Those rows keep a null kind and get one the first time they
are inspected -- which is also what happens to a record whose file could not be
read.

Done in three queryset updates rather than row by row: this runs over every
measurement in the database.
"""

from django.db import migrations

# Registry keys, spelled out rather than imported. A migration has to keep
# describing the past even if the registry's built-in types are renamed or removed.
TOPOGRAPHY_MAP = "topography-map"
UNIFORM_LINE_SCAN = "uniform-line-scan"
NONUNIFORM_LINE_SCAN = "nonuniform-line-scan"


def backfill_kind(apps, schema_editor):
    Measurement = apps.get_model("manager", "Measurement")
    inspected = Measurement.objects.filter(resolution_x__isnull=False, kind__isnull=True)

    inspected.filter(resolution_y__isnull=False).update(kind=TOPOGRAPHY_MAP)
    inspected.filter(resolution_y__isnull=True, is_periodic_editable=False).update(
        kind=NONUNIFORM_LINE_SCAN
    )
    inspected.filter(resolution_y__isnull=True, is_periodic_editable=True).update(
        kind=UNIFORM_LINE_SCAN
    )


def clear_kind(apps, schema_editor):
    Measurement = apps.get_model("manager", "Measurement")
    Measurement.objects.update(kind=None)


class Migration(migrations.Migration):

    dependencies = [
        ("manager", "0087_measurement_kind"),
    ]

    operations = [
        migrations.RunPython(backfill_kind, clear_kind),
    ]
