"""
Rename `WorkflowResult.subject_topography` to `subject_measurement`.

This is a rename, not a drop-and-add: the column holds the subject of every
measurement-level analysis ever computed.

The subject-type tag stored inside `subject_hash` deliberately keeps saying
"topography". It is opaque, never shown to users, and rewriting it would mean
recomputing the hash of every row for no benefit (see
`WorkflowResult.update_subject_hash`).
"""

from django.db import migrations, models
import django.db.models.deletion

import topobank.analysis.models


class Migration(migrations.Migration):

    dependencies = [
        ("analysis", "0065_resultzipcontainer"),
        # The target model must have been renamed first.
        ("manager", "0086_rename_topography_measurement"),
    ]

    operations = [
        # The index references the field, so it goes first and is recreated after.
        migrations.RemoveIndex(
            model_name="workflowresult", name="result_func_topo_time_idx"
        ),
        migrations.RenameField(
            model_name="workflowresult",
            old_name="subject_topography",
            new_name="subject_measurement",
        ),
        migrations.AlterField(
            model_name="workflowresult",
            name="subject_measurement",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=topobank.analysis.models.cascade_or_set_null,
                related_name="workflow_results",
                to="manager.measurement",
            ),
        ),
        migrations.AddIndex(
            model_name="workflowresult",
            index=models.Index(
                fields=["workflow_name", "subject_measurement", "-task_start_time"],
                name="result_func_topo_time_idx",
            ),
        ),
    ]
