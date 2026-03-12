# Rename the Folder model to ManifestList.
# RenameModel handles renaming the table (files_folder -> files_manifestlist)
# and updating all FK references automatically.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('files', '0009_rename_upload_confirmed_manifest_confirmed_at'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Folder',
            new_name='ManifestList',
        ),
    ]
