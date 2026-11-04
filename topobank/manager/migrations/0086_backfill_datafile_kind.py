from django.db import migrations


def mark_datafiles_raw(apps, schema_editor):
    """Give every measurement's data file the kind ``raw``.

    Zip imports used to create the data file's manifest without a kind, so it
    carried the default ``N/A``. The processing of a measurement is started from
    its data file (see ``topobank.manager.uploads.dispatch_processing``), which
    only looks at ``raw`` manifests.
    """
    Manifest = apps.get_model("files", "Manifest")
    Manifest.objects.filter(topography_datafiles__isnull=False).exclude(
        kind="raw"
    ).update(kind="raw")


class Migration(migrations.Migration):
    dependencies = [
        ("manager", "0085_rename_deletion_time_to_deleted_at"),
    ]

    operations = [
        migrations.RunPython(mark_datafiles_raw, migrations.RunPython.noop),
    ]
