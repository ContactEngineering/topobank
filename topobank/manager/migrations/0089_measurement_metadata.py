"""
Add `Measurement.metadata` and `Measurement.file_info`.

The two JSON documents that replace the typed metadata columns. `0090` fills them
in; the columns themselves are dropped separately, once the backfill has been seen
to be right on real data.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("manager", "0088_backfill_measurement_kind"),
    ]

    operations = [
        migrations.AddField(
            model_name="measurement",
            name="metadata",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="measurement",
            name="file_info",
            field=models.JSONField(default=dict),
        ),
    ]
