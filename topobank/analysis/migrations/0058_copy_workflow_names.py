"""
Data migration: copy workflow names from FK fields to the new CharField columns.
"""
from django.db import migrations


def copy_workflow_names_forward(apps, schema_editor):
    Workflow = apps.get_model('analysis', 'Workflow')
    WorkflowResult = apps.get_model('analysis', 'WorkflowResult')
    WorkflowTemplate = apps.get_model('analysis', 'WorkflowTemplate')

    # There is one Workflow row per registered implementation (a handful), so a
    # set-based UPDATE per workflow is far cheaper than iterating over results.
    for pk, name in Workflow.objects.values_list('pk', 'name').iterator():
        # Copy WorkflowResult.function.name → WorkflowResult.workflow_name
        WorkflowResult.objects.filter(
            function_id=pk, workflow_name__isnull=True
        ).update(workflow_name=name)
        # Copy WorkflowTemplate.implementation.name → .implementation_name
        WorkflowTemplate.objects.filter(
            implementation_id=pk, implementation_name__isnull=True
        ).update(implementation_name=name)


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0057_add_workflow_name_fields'),
    ]

    operations = [
        migrations.RunPython(copy_workflow_names_forward, migrations.RunPython.noop),
    ]
