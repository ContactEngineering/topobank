# Generated by Django 4.2.7 on 2024-01-19 13:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('manager', '0046_topography_task_memory'),
    ]

    operations = [
        migrations.AlterField(
            model_name='topography',
            name='task_memory',
            field=models.BigIntegerField(null=True),
        ),
    ]
