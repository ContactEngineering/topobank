# Generated by Django 3.2.11 on 2022-03-30 20:02

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0008_auto_20210510_1252'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='analysis',
            name='result',
        ),
    ]
