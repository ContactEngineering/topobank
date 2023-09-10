from django.contrib.contenttypes.models import ContentType
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('manager', '0033_surfacecollection'),
        ('analysis', '0018_auto_20230901_2303'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='analysis',
            name='subject_id',
        ),
        migrations.RemoveField(
            model_name='analysis',
            name='subject_type',
        ),
    ]
