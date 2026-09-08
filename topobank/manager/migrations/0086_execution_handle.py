from django.db import migrations, models


class Migration(migrations.Migration):
    """Record the workflow manager handle of a run on every task-state row."""

    dependencies = [
        ("manager", "0085_rename_deletion_time_to_deleted_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="topography",
            name="execution_handle",
            field=models.JSONField(null=True),
        ),
        migrations.AddField(
            model_name="zipcontainer",
            name="execution_handle",
            field=models.JSONField(null=True),
        ),
    ]
