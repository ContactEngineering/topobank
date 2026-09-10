from django.db import migrations, models


class Migration(migrations.Migration):
    """Record which workflow manager launched a result, and its handle to the run."""

    dependencies = [
        ("analysis", "0066_workflowresult_soft_delete"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowresult",
            name="execution_handle",
            field=models.JSONField(null=True),
        ),
    ]
