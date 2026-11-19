from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("analysis", "0066_workflowresult_soft_delete"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowresult",
            name="task_wait_deadline",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
