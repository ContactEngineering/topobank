from django.db import migrations, models


class Migration(migrations.Migration):
    """Record the workflow manager handle of a run on every task-state row."""

    dependencies = [
        ("analysis", "0066_workflowresult_soft_delete"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowresult",
            name="execution_handle",
            field=models.JSONField(null=True),
        ),
        migrations.AddField(
            model_name="resultzipcontainer",
            name="execution_handle",
            field=models.JSONField(null=True),
        ),
    ]
