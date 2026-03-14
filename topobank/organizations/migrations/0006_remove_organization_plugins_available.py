from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0005_fix_plugins_available_data'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='organization',
            name='plugins_available',
        ),
    ]
