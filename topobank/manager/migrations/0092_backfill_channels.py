"""
Backfill `file_info["channels"]` from the `channel_names` column.

`channel_names` was a display cache of `(name, unit)` pairs rebuilt on every
inspection. The inventory it becomes records more per channel -- dimensionality,
lateral and data units, the kind that would import it -- but only a re-inspection
can supply those, so this writes what the pairs know: the name, the data unit,
and the occurrence ordinal, which is derived purely from the names (`None` unless
a name is duplicated within the file). Everything else stays `None` until the
measurement is inspected again; the schema treats `None` as "not recorded".

Measurements that were never inspected have an empty `channel_names` and are left
alone. The document is written unvalidated and the schema deliberately not
imported, for the same reason as in `0090`: a migration has to keep describing
the past.

Done in batches with `bulk_update`: this runs over every measurement.
"""

from collections import Counter

from django.db import migrations

BATCH_SIZE = 500


def channels_from_names(channel_names):
    """The inventory entries the legacy `(name, unit)` pairs can supply."""
    counts = Counter(name for name, _unit in channel_names)
    seen = Counter()
    channels = []
    for name, unit in channel_names:
        occurrence = None
        if counts[name] > 1:
            occurrence = seen[name]
            seen[name] += 1
        channels.append(
            {
                "name": name,
                "occurrence": occurrence,
                "dim": None,
                "unit": None,
                "data_unit": unit,
                "kind": None,
            }
        )
    return channels


def backfill_channels(apps, schema_editor):
    Measurement = apps.get_model("manager", "Measurement")
    batch = []
    queryset = Measurement.objects.exclude(channel_names=[]).only(
        "id", "channel_names", "file_info"
    )
    for measurement in queryset.iterator(chunk_size=BATCH_SIZE):
        file_info = dict(measurement.file_info or {})
        file_info["channels"] = channels_from_names(measurement.channel_names)
        measurement.file_info = file_info
        batch.append(measurement)
        if len(batch) >= BATCH_SIZE:
            Measurement.objects.bulk_update(batch, ["file_info"])
            batch = []
    if batch:
        Measurement.objects.bulk_update(batch, ["file_info"])


def clear_channels(apps, schema_editor):
    Measurement = apps.get_model("manager", "Measurement")
    batch = []
    queryset = Measurement.objects.filter(file_info__has_key="channels").only(
        "id", "file_info"
    )
    for measurement in queryset.iterator(chunk_size=BATCH_SIZE):
        file_info = dict(measurement.file_info)
        file_info.pop("channels", None)
        measurement.file_info = file_info
        batch.append(measurement)
        if len(batch) >= BATCH_SIZE:
            Measurement.objects.bulk_update(batch, ["file_info"])
            batch = []
    if batch:
        Measurement.objects.bulk_update(batch, ["file_info"])


class Migration(migrations.Migration):

    dependencies = [
        ("manager", "0091_rename_legacy_metadata_columns"),
    ]

    operations = [
        migrations.RunPython(backfill_channels, clear_channels),
    ]
