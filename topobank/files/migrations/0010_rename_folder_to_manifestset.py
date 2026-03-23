# Generated manually for renaming Folder model to ManifestSet

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('files', '0009_rename_upload_confirmed_manifest_confirmed_at'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Folder',
            new_name='ManifestSet',
        ),
    ]
