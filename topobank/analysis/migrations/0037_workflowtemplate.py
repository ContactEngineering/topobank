# Generated by Django 4.2.18 on 2025-04-27 22:27

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import topobank.authorization.mixins


class Migration(migrations.Migration):

    dependencies = [
        ('authorization', '0001_initial'),
        ('analysis', '0036_analysis_description'),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkflowTemplate',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('kwargs', models.JSONField(blank=True, default=dict)),
                ('creator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('implementation', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='analysis.analysisfunction')),
                ('permissions', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='authorization.permissionset')),
            ],
            bases=(topobank.authorization.mixins.PermissionMixin, models.Model),
        ),
    ]
