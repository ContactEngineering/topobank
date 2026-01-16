# Generated for performance optimization
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('manager', '0072_rename_creation_time_surface_created_at_and_more'),
    ]

    operations = [
        # Add index on name for ordering
        migrations.AddIndex(
            model_name='surface',
            index=models.Index(fields=['name'], name='surface_name_idx'),
        ),
        # Add composite index for the common query pattern (filter + order)
        migrations.AddIndex(
            model_name='surface',
            index=models.Index(fields=['deletion_time', 'name'], name='surface_list_idx'),
        ),
        # Add partial index for active surfaces (most common query)
        # This creates: CREATE INDEX ... WHERE deletion_time IS NULL
        migrations.RunSQL(
            sql="""
                CREATE INDEX surface_active_name_idx
                ON manager_surface (name)
                WHERE deletion_time IS NULL;
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS surface_active_name_idx;
            """,
        ),
    ]
