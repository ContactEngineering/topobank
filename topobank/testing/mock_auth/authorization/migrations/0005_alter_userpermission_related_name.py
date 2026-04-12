# Generated migration to update UserPermission related_name and add unique_together

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authorization', '0004_alter_userpermission_user'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userpermission',
            name='parent',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='user_permissions',
                to='authorization.permissionset',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='userpermission',
            unique_together={('parent', 'user')},
        ),
    ]
