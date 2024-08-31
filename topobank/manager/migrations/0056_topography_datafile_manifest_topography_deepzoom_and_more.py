# Generated by Django 4.2.15 on 2024-08-28 11:34

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("files", "0003_rename_file_name_manifest_filename_and_more"),
        ("manager", "0055_alter_surfaceuserobjectpermission_unique_together_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="topography",
            name="datafile_manifest",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="topography_datafiles",
                to="files.manifest",
            ),
        ),
        migrations.AddField(
            model_name="topography",
            name="deepzoom",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="topography_deepzooms",
                to="files.folder",
            ),
        ),
        migrations.AddField(
            model_name="topography",
            name="squeezed_datafile_manifest",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="topography_squeezed_datafiles",
                to="files.manifest",
            ),
        ),
        migrations.AddField(
            model_name="topography",
            name="thumbnail_manifest",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="topography_thumbnails",
                to="files.manifest",
            ),
        ),
    ]