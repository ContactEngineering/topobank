from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("analysis", "0054_alter_workflowresult_subject_dispatch"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workflow",
            name="name",
            field=models.TextField(help_text="Internal unique identifier", unique=True),
        ),
    ]
