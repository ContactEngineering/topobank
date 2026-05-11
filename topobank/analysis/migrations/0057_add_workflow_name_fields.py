"""
Add workflow_name CharField to WorkflowResult and implementation_name CharField to
WorkflowTemplate. These replace the former ForeignKey references to the Workflow DB model.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0056_workflowresult_permissions_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='workflowresult',
            name='workflow_name',
            field=models.CharField(db_index=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='workflowtemplate',
            name='implementation_name',
            field=models.CharField(max_length=255, null=True),
        ),
    ]
