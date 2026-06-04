import hashlib

from django.db import migrations


def compute_hash(subject_type, subject_ids):
    sorted_ids = sorted(set(subject_ids))
    key = ",".join(str(i) for i in sorted_ids)
    return f"{subject_type}:{hashlib.sha256(key.encode()).hexdigest()}"


def backfill_subject_hash(apps, schema_editor):
    WorkflowResult = apps.get_model("analysis", "WorkflowResult")
    to_update = []
    for wr in WorkflowResult.objects.filter(subject_hash__isnull=True).iterator():
        if wr.subject_topography_id is not None:
            wr.subject_hash = compute_hash("topography", [wr.subject_topography_id])
        elif wr.subject_surface_id is not None:
            wr.subject_hash = compute_hash("surface", [wr.subject_surface_id])
        elif wr.subject_tag_id is not None:
            wr.subject_hash = compute_hash("tag", [wr.subject_tag_id])
        else:
            continue
        to_update.append(wr)
        if len(to_update) >= 500:
            WorkflowResult.objects.bulk_update(to_update, ["subject_hash"])
            to_update = []
    if to_update:
        WorkflowResult.objects.bulk_update(to_update, ["subject_hash"])


class Migration(migrations.Migration):

    dependencies = [
        ("analysis", "0063_alter_workflowresult_surfaces"),
    ]

    operations = [
        migrations.RunPython(backfill_subject_hash, migrations.RunPython.noop),
    ]
