"""
Add the generic metadata fields to `Measurement`.

Metadata moves out of typed columns into two JSON documents validated by the
measurement type's pydantic schemas (`metadata` for what the user edits,
`file_info` for what the inspection derives from the data file), and the data
channel is identified by name rather than by position. The legacy columns are
still present at this point; they are read by the backfill in the next migration
and dropped afterwards.
"""

import django.db.models.fields.json
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("manager", "0084_rename_topography_measurement"),
    ]

    operations = [
        migrations.AddField(
            model_name="measurement",
            name="channel_index_hint",
            field=models.PositiveIntegerField(default=None, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="measurement",
            name="channel_name",
            field=models.TextField(blank=True, default=None, null=True),
        ),
        migrations.AddField(
            model_name="measurement",
            name="channel_occurrence",
            field=models.PositiveIntegerField(default=None, null=True),
        ),
        migrations.AddField(
            model_name="measurement",
            name="file_info",
            field=models.JSONField(default=dict, editable=False),
        ),
        migrations.AddField(
            model_name="measurement",
            name="kind",
            field=models.CharField(
                blank=True, db_index=True, default="", max_length=64
            ),
        ),
        migrations.AddField(
            model_name="measurement",
            name="metadata",
            field=models.JSONField(default=dict),
        ),
        migrations.AddIndex(
            model_name="measurement",
            index=models.Index(fields=["kind"], name="measurement_kind_idx"),
        ),
        migrations.AddConstraint(
            model_name="measurement",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "kind",
                        django.db.models.fields.json.KeyTextTransform(
                            "kind", "metadata"
                        ),
                    )
                ),
                name="measurement_kind_matches_metadata",
            ),
        ),
    ]
