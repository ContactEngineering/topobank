# Generated manually for renaming Folder model to ManifestSet

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('files', '0009_rename_upload_confirmed_manifest_confirmed_at'),
        # Not data dependencies: these are the last migrations in other apps
        # whose frozen operations reference this model by its old name
        # ("files.folder"). The migration executor threads one project state
        # through a topological sort of the whole graph, and nothing else
        # pins these before the rename — if the sort ever emits the rename
        # first (new migrations elsewhere can reshuffle it), replaying them
        # fails with "Related model 'files.folder' cannot be resolved".
        ('analysis', '0026_add_analysis_permissions_folder'),
        ('manager', '0056_topography_datafile_manifest_topography_deepzoom_and_more'),
        ('manager', '0060_surface_attachments_topography_attachments'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Folder',
            new_name='ManifestSet',
        ),
    ]
