"""
Add `Measurement.kind`.

The column records which registered measurement adapter is used for a record. It
stays null for measurements whose data file has not been inspected yet; `0086`
fills it in for those that have.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("manager", "0086_rename_topography_measurement"),
    ]

    operations = [
        migrations.AddField(
            model_name="measurement",
            name="kind",
            field=models.TextField(blank=True, editable=False, null=True),
        ),
    ]
