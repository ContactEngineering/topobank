"""
Backfill `file_info["channels"]` from the `channel_names` column.

`channel_names` was a display cache of `(name, unit)` pairs rebuilt on every
inspection. The inventory it becomes records more per channel -- dimensionality,
lateral and data units, the kind that would import it -- but only a re-inspection
can supply those, so this writes what the pairs know: the name, the data unit,
and the occurrence ordinal, which is derived purely from the names (`None` unless
a name is duplicated within the file). Everything else stays `None` until the
measurement is inspected again; the schema treats `None` as "not recorded".

Measurements with an empty `channel_names` are left alone, and that is two
populations, not one. Measurements never inspected have nothing to record. But
`channel_names` was only added in `0035` (September 2023), without a backfill, so
a measurement inspected before then and not since is fully inspected -- `0090`
gave it a `file_info` -- and still has no names. There is nothing to derive an
inventory from for those rows; only a re-inspection can supply one, and a
migration is not the place to dispatch that. The same rows will not be able to
convert their positional `data_source` into a channel name later, for the same
reason, so the re-inspection is a prerequisite of that step rather than of this
one. They can be counted with
``Measurement.objects.filter(channel_names=[]).exclude(file_info={})``.

The document is written unvalidated and the schema deliberately not imported, for
the same reason as in `0090`: a migration has to keep describing the past.

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
