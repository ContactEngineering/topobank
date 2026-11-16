from django.db import migrations

# Kept literal: a migration must not depend on code that may change later
MEMORY_REFUSAL_KEY = "memory_refusal"
REFUSAL_MESSAGE_PREFIX = "This analysis is predicted to need about "


def mark_memory_refusals(apps, schema_editor):
    """
    Mark results refused by the memory guard before refusals were recorded in
    their metadata, so that they are tried again.

    Many of them were refused by a faulty estimate (#1393) and would otherwise
    stand forever: a failed result counts as present, so it is never resubmitted
    automatically, and anonymous visitors cannot renew it (#1406). Marked with
    their original time, they are past the retry interval and are resubmitted on
    the next view.
    """
    WorkflowResult = apps.get_model("analysis", "WorkflowResult")
    refused = WorkflowResult.objects.filter(
        task_state="fa", task_error__startswith=REFUSAL_MESSAGE_PREFIX
    )
    for result in refused.iterator():
        metadata = result.metadata or {}
        if MEMORY_REFUSAL_KEY in metadata:
            continue
        refused_at = result.task_end_time or result.updated_at or result.created_at
        metadata[MEMORY_REFUSAL_KEY] = {
            "estimate": None,
            "budget": None,
            "refused_at": refused_at.isoformat() if refused_at else None,
        }
        WorkflowResult.objects.filter(pk=result.pk).update(metadata=metadata)


class Migration(migrations.Migration):
    dependencies = [
        ("analysis", "0066_workflowresult_soft_delete"),
    ]

    operations = [
        migrations.RunPython(mark_memory_refusals, migrations.RunPython.noop),
    ]
