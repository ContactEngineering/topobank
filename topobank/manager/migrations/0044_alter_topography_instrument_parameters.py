# Generated by Django 3.2.18 on 2023-11-19 17:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('manager', '0043_topography_is_periodic_editable'),
    ]

    operations = [
        migrations.AlterField(
            model_name='topography',
            name='instrument_parameters',
            field=models.JSONField(default=dict),
        ),
    ]
