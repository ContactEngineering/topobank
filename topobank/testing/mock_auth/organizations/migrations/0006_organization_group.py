# Generated migration for adding group field to mock Organization

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('organizations', '0005_fix_plugins_available_data'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='group',
            field=models.OneToOneField(
                help_text='Group which corresponds to members of this organization.',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to='auth.group',
            ),
        ),
    ]
