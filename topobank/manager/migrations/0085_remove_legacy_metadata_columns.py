"""
Drop the metadata columns that have moved into `Measurement.metadata` and
`Measurement.file_info`.

Runs after the backfill, which is the only reader of these columns. This is also
where the reverse accessors of the file foreign keys are renamed
(``manifest.topography_datafiles`` becomes ``manifest.measurement_datafiles`` and
so on): that needs to refer to the manifest models, and only here is the `files`
app guaranteed to have been migrated far enough to provide them under their
current names.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("files", "0010_rename_folder_to_manifestset"),
        ("manager", "0084_backfill_measurement_metadata"),
    ]

    operations = [
        # `related_name` is state-only; no database operation corresponds to it.
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="measurement",
                    name="datafile",
                    field=models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="measurement_datafiles",
                        to="files.manifest",
                    ),
                ),
                migrations.AlterField(
                    model_name="measurement",
                    name="squeezed_datafile",
                    field=models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="measurement_squeezed_datafiles",
                        to="files.manifest",
                    ),
                ),
                migrations.AlterField(
                    model_name="measurement",
                    name="thumbnail",
                    field=models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="measurement_thumbnails",
                        to="files.manifest",
                    ),
                ),
                migrations.AlterField(
                    model_name="measurement",
                    name="deepzoom",
                    field=models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="measurement_deepzooms",
                        to="files.manifestset",
                    ),
                ),
            ],
        ),
        migrations.RemoveField(
            model_name="measurement",
            name="bandwidth_lower",
        ),
        migrations.RemoveField(
            model_name="measurement",
            name="bandwidth_upper",
        ),
        migrations.RemoveField(
            model_name="measurement",
            name="channel_names",
        ),
        migrations.RemoveField(
            model_name="measurement",
            name="data_source",
        ),
        migrations.RemoveField(
            model_name="measurement",
            name="detrend_mode",
        ),
        migrations.RemoveField(
            model_name="measurement",
            name="fill_undefined_data_mode",
        ),
        migrations.RemoveField(
            model_name="measurement",
            name="has_undefined_data",
        ),
        migrations.RemoveField(
            model_name="measurement",
            name="height_scale",
        ),
        migrations.RemoveField(
            model_name="measurement",
            name="height_scale_editable",
        ),
        migrations.RemoveField(
            model_name="measurement",
            name="instrument_name",
        ),
        migrations.RemoveField(
            model_name="measurement",
            name="instrument_parameters",
        ),
        migrations.RemoveField(
            model_name="measurement",
            name="instrument_type",
        ),
        migrations.RemoveField(
            model_name="measurement",
            name="is_periodic",
        ),
        migrations.RemoveField(
            model_name="measurement",
            name="is_periodic_editable",
        ),
        migrations.RemoveField(
            model_name="measurement",
            name="resolution_x",
        ),
        migrations.RemoveField(
            model_name="measurement",
            name="resolution_y",
        ),
        migrations.RemoveField(
            model_name="measurement",
            name="short_reliability_cutoff",
        ),
        migrations.RemoveField(
            model_name="measurement",
            name="size_editable",
        ),
        migrations.RemoveField(
            model_name="measurement",
            name="size_x",
        ),
        migrations.RemoveField(
            model_name="measurement",
            name="size_y",
        ),
        migrations.RemoveField(
            model_name="measurement",
            name="unit",
        ),
        migrations.RemoveField(
            model_name="measurement",
            name="unit_editable",
        ),
    ]
