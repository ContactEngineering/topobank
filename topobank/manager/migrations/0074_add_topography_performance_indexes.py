# Generated for performance optimization
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('manager', '0073_add_performance_indexes'),
    ]

    operations = [
        # Add index on surface_id for JOIN optimization when filtering surface__deletion_time
        migrations.AddIndex(
            model_name='topography',
            index=models.Index(fields=['surface'], name='topography_surface_idx'),
        ),
        # Add composite index for the common query pattern (filter + order)
        migrations.AddIndex(
            model_name='topography',
            index=models.Index(fields=['deletion_time', 'name'], name='topography_list_idx'),
        ),
        # Add partial index for active topographies (most common query)
        # This creates: CREATE INDEX ... WHERE deletion_time IS NULL
        migrations.RunSQL(
            sql="""
                CREATE INDEX topography_active_name_idx
                ON manager_topography (name)
                WHERE deletion_time IS NULL;
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS topography_active_name_idx;
            """,
        ),
    ]
