"""
Rename `Topography` to `Measurement`.

The model no longer describes only topography data: it is the generic record of a
measurement, whose kind is determined by a registered measurement type (see
:mod:`topobank.measurements`).

Besides the model itself this renames the reverse accessor on `Surface`
(``topography_set`` becomes ``measurements``), the reverse accessors of the file
manifests, and the model's indexes. It also rewrites the model's row in
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
        ("manager", "0081_surface_search_vector_surface_surface_search_idx"),
    ]

    operations = [
        # The old indexes have to go before the rename, because they are declared
        # on the model being renamed.
        migrations.RemoveIndex(
            model_name="topography", name="topography_surface_idx"
        ),
        migrations.RemoveIndex(model_name="topography", name="topography_list_idx"),
        migrations.RemoveIndex(
            model_name="topography", name="topography_active_name_idx"
        ),
        migrations.RenameModel(old_name="Topography", new_name="Measurement"),
        migrations.AlterModelOptions(
            name="measurement",
            options={"ordering": ["measurement_date", "pk"]},
        ),
        migrations.AddIndex(
            model_name="measurement",
            index=models.Index(
                fields=["surface"], name="measurement_surface_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="measurement",
            index=models.Index(
                fields=["deletion_time", "name"], name="measurement_list_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="measurement",
            index=models.Index(
                condition=models.Q(("deletion_time__isnull", True)),
                fields=["name"],
                name="measurement_active_name_idx",
            ),
        ),
        # `surface.topography_set` becomes `surface.measurements`. `related_name`
        # lives only in Django's model state, so this is a state operation with no
        # database counterpart. The reverse accessors of the file foreign keys are
        # renamed in 0085, which is late enough in the graph to refer to the
        # manifest models by their current names.
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
