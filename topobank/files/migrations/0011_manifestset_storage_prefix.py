# Generated manually for adding storage_prefix field to ManifestSet

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('files', '0010_rename_folder_to_manifestset'),
    ]

    operations = [
        migrations.AddField(
            model_name='manifestset',
            name='storage_prefix',
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=512,
                null=True,
                help_text='Content-addressed storage prefix for this manifest set. '
                          'If set, files are stored at {storage_prefix}/{filename}.',
            ),
        ),
    ]
