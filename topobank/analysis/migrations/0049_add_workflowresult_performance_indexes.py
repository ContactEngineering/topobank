# Generated for performance optimization
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0048_alter_workflowresult_description'),
    ]

    operations = [
        # Index on task_start_time for ordering
        migrations.AddIndex(
            model_name='workflowresult',
            index=models.Index(fields=['-task_start_time'], name='result_task_start_idx'),
        ),
        # Composite index for: WHERE task_state = x ORDER BY task_start_time
        # Also used for queries that only filter by task_state (leftmost column)
        migrations.AddIndex(
            model_name='workflowresult',
            index=models.Index(fields=['task_state', '-task_start_time'], name='result_state_time_idx'),
        ),
        # Composite index for: WHERE function = x ORDER BY task_start_time
        # Also used for queries that only filter by function (leftmost column)
        migrations.AddIndex(
            model_name='workflowresult',
            index=models.Index(fields=['function', '-task_start_time'], name='result_workflow_time_idx'),
        ),
        # Partial index for the most common query: active (non-deprecated) results ordered by time
        # This is highly optimized for: WHERE deprecation_time IS NULL ORDER BY task_start_time DESC
        # Smaller than a full index since it only includes rows where deprecation_time IS NULL
        migrations.RunSQL(
            sql="""
                CREATE INDEX result_active_time_idx
                ON analysis_workflowresult (task_start_time DESC)
                WHERE deprecation_time IS NULL;
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS result_active_time_idx;
            """,
        ),
    ]
