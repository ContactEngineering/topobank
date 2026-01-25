from django.db import migrations


class Migration(migrations.Migration):
    """
    Add index on manager_tag.path for case-insensitive prefix matching.

    This improves query performance for tag filtering operations like:
    - WHERE UPPER(path) LIKE 'TEST%'
    - WHERE path ILIKE 'test%'

    The index uses varchar_pattern_ops to support LIKE/prefix queries.
    """

    dependencies = [
        ('manager', '0074_add_topography_performance_indexes'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE INDEX IF NOT EXISTS manager_tag_path_upper_idx
                ON manager_tag (UPPER(path) varchar_pattern_ops);
            """,
            reverse_sql="DROP INDEX IF EXISTS manager_tag_path_upper_idx;",
        ),
    ]
