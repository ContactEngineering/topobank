# Generated by Django 4.2.20 on 2025-05-04 18:18

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0037_workflowtemplate'),
    ]

    operations = [
        migrations.RenameField(
            model_name='analysis',
            old_name='end_time',
            new_name='task_end_time',
        ),
        migrations.RenameField(
            model_name='analysis',
            old_name='start_time',
            new_name='task_start_time',
        ),
        migrations.AddField(
            model_name='analysis',
            name='task_submission_time',
            field=models.DateTimeField(null=True),
        ),
        migrations.AlterField(
            model_name='analysis',
            name='creation_time',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
    ]
