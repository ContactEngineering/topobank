# Generated for performance optimization
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authorization', '0002_organizationpermission'),
    ]

    operations = [
        # Add composite index on UserPermission for permission lookups
        migrations.AddIndex(
            model_name='userpermission',
            index=models.Index(fields=['user', 'parent'], name='userperm_user_parent_idx'),
        ),
        # Add index on parent for reverse lookups (from PermissionSet)
        migrations.AddIndex(
            model_name='userpermission',
            index=models.Index(fields=['parent'], name='userperm_parent_idx'),
        ),
        # Add composite index on OrganizationPermission for permission lookups
        migrations.AddIndex(
            model_name='organizationpermission',
            index=models.Index(fields=['organization', 'parent'], name='orgperm_org_parent_idx'),
        ),
        # Add index on parent for reverse lookups (from PermissionSet)
        migrations.AddIndex(
            model_name='organizationpermission',
            index=models.Index(fields=['parent'], name='orgperm_parent_idx'),
        ),
    ]
