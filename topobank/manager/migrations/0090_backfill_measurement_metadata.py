"""
Backfill `Measurement.metadata` and `Measurement.file_info` from the columns.

Every field moves to exactly one of the two documents, decided by who writes it:
metadata is what a user can edit, `file_info` is what inspecting the data file
produced. The `*_editable` flags are file-derived despite their name -- they record
whether the *file* supplied a value, not a user preference.

Which fields a document may contain depends on the measurement's kind, so this
walks the same three shapes the schemas describe. Measurements with no kind (never
inspected) and measurements whose kind is not one of the built-ins (created by a
plugin) are left alone: nothing here knows what their documents should look like,
and their columns are still present for whatever does.

The schemas are deliberately not imported. A migration has to keep describing the
past, and importing a schema would make this file's behaviour change whenever a
field is added or renamed. The documents are assembled as plain dicts and the
column values are written through unvalidated -- they came out of columns that
enforced the same choices.

Done in batches with `bulk_update`: this runs over every measurement in the
database.
"""

from django.db import migrations

#: Registry keys, spelled out rather than imported (see the module docstring).
TOPOGRAPHY_MAP = "topography-map"
UNIFORM_LINE_SCAN = "uniform-line-scan"
NONUNIFORM_LINE_SCAN = "nonuniform-line-scan"

#: Metadata every height kind has.
HEIGHT_METADATA = ["size_x", "unit", "height_scale", "detrend_mode"]
#: Metadata the kinds that support periodicity have, on top of the above.
PERIODIC_METADATA = ["is_periodic", "fill_undefined_data_mode"]
#: File-derived values every height kind has.
HEIGHT_FILE_INFO = [
    "resolution_x",
    "bandwidth_lower",
    "bandwidth_upper",
    "short_reliability_cutoff",
    "has_undefined_data",
    "undefined_data_fraction",
    "detrend_parameters",
    "size_editable",
    "unit_editable",
    "height_scale_editable",
    "is_periodic_editable",
]

#: Which fields each kind's two documents hold.
SHAPES = {
    TOPOGRAPHY_MAP: (
        HEIGHT_METADATA + ["size_y"] + PERIODIC_METADATA,
        HEIGHT_FILE_INFO + ["resolution_y"],
    ),
    UNIFORM_LINE_SCAN: (
        HEIGHT_METADATA + PERIODIC_METADATA,
        HEIGHT_FILE_INFO,
    ),
    # A nonuniform line scan supports neither periodicity nor filling, so those
    # fields have nowhere to go and are dropped. `is_periodic` was forced to False
    # on inspection anyway, and `fill_undefined_data_mode` was never applied.
    NONUNIFORM_LINE_SCAN: (
        HEIGHT_METADATA,
        HEIGHT_FILE_INFO,
    ),
}

BATCH_SIZE = 500


def instrument_document(measurement):
    """The instrument sub-document, which every height kind carries."""
    return {
        "name": measurement.instrument_name or "",
        "type": measurement.instrument_type or "undefined",
        "parameters": measurement.instrument_parameters or {},
    }


def document(measurement, kind, field_names):
    """Assemble one document, omitting fields that are None."""
    values = {"kind": kind}
    for name in field_names:
        value = getattr(measurement, name)
        if value is not None:
            values[name] = value
    return values


def backfill_metadata(apps, schema_editor):
    Measurement = apps.get_model("manager", "Measurement")

    for kind, (metadata_fields, file_info_fields) in SHAPES.items():
        queryset = Measurement.objects.filter(kind=kind)
        batch = []
        for measurement in queryset.iterator(chunk_size=BATCH_SIZE):
            metadata = document(measurement, kind, metadata_fields)
            metadata["instrument"] = instrument_document(measurement)
            measurement.metadata = metadata
            measurement.file_info = document(measurement, kind, file_info_fields)
            batch.append(measurement)
            if len(batch) >= BATCH_SIZE:
                Measurement.objects.bulk_update(batch, ["metadata", "file_info"])
                batch = []
        if batch:
            Measurement.objects.bulk_update(batch, ["metadata", "file_info"])


def clear_metadata(apps, schema_editor):
    """
    Empty both documents again.

    Reversible because the columns are still there: this migration is the only
    writer of the documents, so emptying them restores the previous state exactly.
    """
    Measurement = apps.get_model("manager", "Measurement")
    Measurement.objects.update(metadata={}, file_info={})


class Migration(migrations.Migration):

    dependencies = [
        ("manager", "0089_measurement_metadata"),
    ]

    operations = [
        migrations.RunPython(backfill_metadata, clear_metadata),
    ]
