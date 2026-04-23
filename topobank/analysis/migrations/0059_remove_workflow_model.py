"""
Remove the Workflow database model and its FK references:
- Remove WorkflowResult.function FK (replaced by workflow_name CharField)
- Remove WorkflowTemplate.implementation FK (replaced by implementation_name CharField)
- Delete the Workflow DB model (now a plain Python class)
- Update performance indexes to reference workflow_name instead of function
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0058_copy_workflow_names'),
    ]

    operations = [
        # Remove old indexes that reference the 'function' FK column
        migrations.RemoveIndex(
            model_name='workflowresult',
            name='result_workflow_time_idx',
        ),
        migrations.RemoveIndex(
            model_name='workflowresult',
            name='result_func_subj_time_idx',
        ),
        # Remove the function FK from WorkflowResult
        migrations.RemoveField(
            model_name='workflowresult',
            name='function',
        ),
        # Remove the implementation FK from WorkflowTemplate
        migrations.RemoveField(
            model_name='workflowtemplate',
            name='implementation',
        ),
        # Delete the Workflow DB model (all references have been removed)
        migrations.DeleteModel(
            name='Workflow',
        ),
        # Add new indexes on workflow_name (mirrors the old function-based indexes)
        migrations.AddIndex(
            model_name='workflowresult',
            index=models.Index(
                fields=['workflow_name', '-task_start_time'],
                name='result_workflow_time_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='workflowresult',
            index=models.Index(
                fields=['workflow_name', 'subject_dispatch', '-task_start_time'],
                name='result_func_subj_time_idx',
            ),
        ),
    ]
