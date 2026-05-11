"""
Data migration: copy workflow names from FK fields to the new CharField columns.
"""
from django.db import migrations


def copy_workflow_names_forward(apps, schema_editor):
    WorkflowResult = apps.get_model('analysis', 'WorkflowResult')
    WorkflowTemplate = apps.get_model('analysis', 'WorkflowTemplate')

    # Copy WorkflowResult.function.name → WorkflowResult.workflow_name
    for wr in WorkflowResult.objects.select_related('function').all():
        if wr.function is not None and wr.workflow_name is None:
            wr.workflow_name = wr.function.name
            wr.save(update_fields=['workflow_name'])

    # Copy WorkflowTemplate.implementation.name → WorkflowTemplate.implementation_name
    for wt in WorkflowTemplate.objects.select_related('implementation').all():
        if wt.implementation is not None and wt.implementation_name is None:
            wt.implementation_name = wt.implementation.name
            wt.save(update_fields=['implementation_name'])


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0057_add_workflow_name_fields'),
    ]

    operations = [
        migrations.RunPython(copy_workflow_names_forward, migrations.RunPython.noop),
    ]
