# Generated by Django 2.2.13 on 2020-07-10 09:29

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('manager', '0015_surface_is_published'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='surface',
            options={'ordering': ['name'], 'permissions': (('share_surface', 'Can share surface'), ('publish_surface', 'Can publish surface'))},
        ),
    ]
