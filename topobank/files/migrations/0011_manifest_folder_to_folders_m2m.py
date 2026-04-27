# Generated manually for migrating Manifest.folder FK to folders M2M

from django.db import migrations, models


def migrate_folder_to_folders(apps, schema_editor):
    """Migrate data from folder FK to folders M2M."""
    Manifest = apps.get_model('files', 'Manifest')
    for manifest in Manifest.objects.filter(folder__isnull=False):
        manifest.folders.add(manifest.folder)


def migrate_folders_to_folder(apps, schema_editor):
    """Reverse migration: set folder FK from folders M2M."""
    Manifest = apps.get_model('files', 'Manifest')
    for manifest in Manifest.objects.all():
        first_folder = manifest.folders.first()
        if first_folder:
            manifest.folder = first_folder
            manifest.save(update_fields=['folder'])


class Migration(migrations.Migration):

    dependencies = [
        ('files', '0010_rename_folder_to_manifestset'),
    ]

    operations = [
        # Step 1: Add the new M2M field
        migrations.AddField(
            model_name='manifest',
            name='folders',
            field=models.ManyToManyField(
                blank=True,
                related_name='files_new',
                to='files.manifestset',
            ),
        ),
        # Step 2: Migrate data from FK to M2M
        migrations.RunPython(migrate_folder_to_folders, migrate_folders_to_folder),
        # Step 3: Remove unique_together constraint
        migrations.AlterUniqueTogether(
            name='manifest',
            unique_together=set(),
        ),
        # Step 4: Remove the old FK field
        migrations.RemoveField(
            model_name='manifest',
            name='folder',
        ),
        # Step 5: Change related_name from 'files_new' to 'files'
        migrations.AlterField(
            model_name='manifest',
            name='folders',
            field=models.ManyToManyField(
                blank=True,
                related_name='files',
                to='files.manifestset',
            ),
        ),
    ]
