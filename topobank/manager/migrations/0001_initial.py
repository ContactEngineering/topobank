# Generated by Django 2.1.7 on 2019-04-16 14:50

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import topobank.manager.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Surface',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=80)),
                ('description', models.TextField(blank=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Topography',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=80)),
                ('datafile', models.FileField(max_length=250, upload_to=topobank.manager.models.user_directory_path)),
                ('data_source', models.IntegerField()),
                ('measurement_date', models.DateField()),
                ('description', models.TextField(blank=True)),
                ('size_editable', models.BooleanField(default=False)),
                ('size_x', models.FloatField()),
                ('size_y', models.FloatField(null=True)),
                ('unit_editable', models.BooleanField(default=False)),
                ('unit', models.TextField(choices=[('km', 'kilometers'), ('m', 'meters'), ('mm', 'millimeters'), ('µm', 'micrometers'), ('nm', 'nanometers'), ('Å', 'angstrom')])),
                ('height_scale_editable', models.BooleanField(default=False)),
                ('height_scale', models.FloatField(default=1)),
                ('detrend_mode', models.TextField(choices=[('center', 'No detrending'), ('height', 'Remove tilt'), ('curvature', 'Remove curvature')], default='center')),
                ('resolution_x', models.IntegerField(null=True)),
                ('resolution_y', models.IntegerField(null=True)),
                ('surface', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='manager.Surface')),
            ],
        ),
    ]
