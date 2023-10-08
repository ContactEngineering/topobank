# Generated by Django 3.2.18 on 2023-09-15 20:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0019_remove_content_type_subject'),
    ]

    operations = [
        migrations.AlterField(
            model_name='analysis',
            name='task_state',
            field=models.CharField(choices=[('pe', 'pending'), ('st', 'started'), ('re', 'retry'), ('fa', 'failure'), ('su', 'success')], max_length=7, null=True),
        ),
    ]