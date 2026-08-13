"""
Rename `Topography` to `Measurement`.

The model is the generic record of a measurement -- identity, permissions, files
and task state -- rather than something specific to topography data. Presently
every measurement still holds height data; this only renames it.

Besides the model itself this renames the reverse accessor on `Surface`
(``topography_set`` becomes ``measurements``). It also rewrites the model's row in
`django_content_type`: Django's `RenameModel` does not touch that table, and
anything referring to a measurement through a generic foreign key - notifications,
most importantly - resolves through it.
"""

from django.db import migrations, models
import django.db.models.deletion


def rename_content_type(apps, schema_editor):
    """
    Point the existing content type at the new model name.

    Updating the row in place (rather than letting `get_for_model` create a new
    one) keeps its primary key, and with it every generic foreign key that
    already refers to a measurement.
    """
    ContentType = apps.get_model("contenttypes", "ContentType")
    ContentType.objects.filter(app_label="manager", model="topography").update(
        model="measurement"
    )
    # The content-type cache may already hold the old name in a long-running
    # process (e.g. when migrations run inside a web worker).
    ContentType.objects.clear_cache()


def restore_content_type(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    ContentType.objects.filter(app_label="manager", model="measurement").update(
        model="topography"
    )
    ContentType.objects.clear_cache()


class Migration(migrations.Migration):

    dependencies = [
        # Older `analysis` migrations refer to `manager.topography` by name, so
        # they all have to have run before the model is renamed out from under
        # them.
        ("analysis", "0064_backfill_subject_hash"),
        ("contenttypes", "0002_remove_content_type_name"),
        # `main`'s `0084`/`0085` refer to `manager.topography` by name, so they have
        # to run before the model is renamed out from under them.
        ("manager", "0085_rename_deletion_time_to_deleted_at"),
    ]

    operations = [
        migrations.RenameModel(old_name="Topography", new_name="Measurement"),
        # `surface.topography_set` becomes `surface.measurements`. `related_name`
        # lives only in Django's model state, so this is a state operation with no
        # database counterpart. The reverse accessors of the file manifests
        # (`manifest.topography_datafiles` and friends) are deliberately left
        # alone: renaming them would pull the `files` app forward in the migration
        # graph, and nothing about the model rename requires it.
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="measurement",
                    name="surface",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="measurements",
                        to="manager.surface",
                    ),
                ),
            ],
        ),
        migrations.RunPython(rename_content_type, restore_content_type),
    ]
