# Generated by Django 2.1.7 on 2019-07-29 14:54

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Configuration',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('valid_since', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='Dependency',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('import_name', models.CharField(max_length=30, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='Version',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('major', models.SmallIntegerField()),
                ('minor', models.SmallIntegerField()),
                ('micro', models.SmallIntegerField(null=True)),
                ('dependency', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='analysis.Dependency')),
            ],
        ),
        migrations.AddField(
            model_name='configuration',
            name='versions',
            field=models.ManyToManyField(to='analysis.Version'),
        ),
        migrations.AddField(
            model_name='analysis',
            name='configuration',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='analysis.Configuration'),
        ),
    ]
