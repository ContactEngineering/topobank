"""
Remove the WorkflowTemplate database model.
WorkflowTemplate was never exposed via REST API and is not used anywhere.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0059_remove_workflow_model'),
    ]

    operations = [
        migrations.DeleteModel(
            name='WorkflowTemplate',
        ),
    ]
