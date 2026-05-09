"""
Collapse WorkflowSubject into WorkflowResult.

The three nullable FKs (topography, surface, tag) that previously lived on the
WorkflowSubject dispatch table are moved directly onto WorkflowResult.  This
eliminates the join and simplifies every query that filters by subject.
"""
import django.db.models.deletion
from django.db import migrations, models

import topobank.analysis.models


def copy_subject_dispatch_to_fks(apps, schema_editor):
    WorkflowResult = apps.get_model("analysis", "WorkflowResult")
    for wr in WorkflowResult.objects.select_related("subject_dispatch").filter(
        subject_dispatch__isnull=False
    ).iterator():
        sd = wr.subject_dispatch
        if sd.topography_id is not None:
            wr.subject_topography_id = sd.topography_id
        elif sd.surface_id is not None:
            wr.subject_surface_id = sd.surface_id
        elif sd.tag_id is not None:
            wr.subject_tag_id = sd.tag_id
        wr.save(update_fields=["subject_topography_id", "subject_surface_id", "subject_tag_id"])


def restore_subject_dispatch(apps, schema_editor):
    WorkflowResult = apps.get_model("analysis", "WorkflowResult")
    WorkflowSubject = apps.get_model("analysis", "WorkflowSubject")
    for wr in WorkflowResult.objects.filter(
        models.Q(subject_topography__isnull=False)
        | models.Q(subject_surface__isnull=False)
        | models.Q(subject_tag__isnull=False)
    ).iterator():
        sd = WorkflowSubject.objects.create(
            topography_id=wr.subject_topography_id,
            surface_id=wr.subject_surface_id,
            tag_id=wr.subject_tag_id,
        )
        wr.subject_dispatch = sd
        wr.save(update_fields=["subject_dispatch"])


class Migration(migrations.Migration):

    dependencies = [
        ("analysis", "0061_merge_20260508_1756"),
        ("manager", "0078_surface_surface_active_name_idx_and_more"),
    ]

    operations = [
        # Step 1 – add the three new FK columns (all nullable)
        migrations.AddField(
            model_name="workflowresult",
            name="subject_topography",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="workflow_results",
                to="manager.topography",
            ),
        ),
        migrations.AddField(
            model_name="workflowresult",
            name="subject_surface",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="workflow_results",
                to="manager.surface",
            ),
        ),
        migrations.AddField(
            model_name="workflowresult",
            name="subject_tag",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="workflow_results",
                to="manager.tag",
            ),
        ),
        # Step 2 – copy data from subject_dispatch → new columns
        migrations.RunPython(
            copy_subject_dispatch_to_fks,
            reverse_code=restore_subject_dispatch,
        ),
        # Step 3 – drop old composite index that referenced subject_dispatch
        migrations.RemoveIndex(
            model_name="workflowresult",
            name="result_func_subj_time_idx",
        ),
        # Step 4 – remove subject_dispatch FK
        migrations.RemoveField(
            model_name="workflowresult",
            name="subject_dispatch",
        ),
        # Step 5 – delete WorkflowSubject model
        migrations.DeleteModel(
            name="WorkflowSubject",
        ),
        # Step 6 – add new per-subject-type composite indexes
        migrations.AddIndex(
            model_name="workflowresult",
            index=models.Index(
                fields=["workflow_name", "subject_topography", "-task_start_time"],
                name="result_func_topo_time_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="workflowresult",
            index=models.Index(
                fields=["workflow_name", "subject_surface", "-task_start_time"],
                name="result_func_surf_time_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="workflowresult",
            index=models.Index(
                fields=["workflow_name", "subject_tag", "-task_start_time"],
                name="result_func_tag_time_idx",
            ),
        ),
    ]
