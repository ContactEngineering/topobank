# Generated by Django 4.2.15 on 2024-08-23 10:42

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("authorization", "0001_initial"),
        ("files", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="folder",
            name="permissions",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="authorization.permissionset",
            ),
        ),
        migrations.AddField(
            model_name="manifest",
            name="permissions",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="authorization.permissionset",
            ),
        ),
    ]
