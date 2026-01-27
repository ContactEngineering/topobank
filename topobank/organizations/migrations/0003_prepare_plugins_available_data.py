# Generated manually for plugins_available field type change - Part 1: Clean data

from django.db import migrations


def clean_plugins_data(_apps, _schema_editor):  # noqa: ARG001
    """
    Extract valid plugin names from potentially corrupted data.

    Handles various corrupted formats:
    - Character-by-character arrays: ["{", "s", "d", "s", ...}]
    - Escaped quotes: "\"{}\"", "\"\\\"{}\\\"\""
    - Normal CSV: "sds_ml,other_plugin"
    - PostgreSQL array literals: "{sds_ml}"

    Uses regex to extract valid identifiers (e.g., sds_ml, topobank_statistics).
    """
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("""
            UPDATE organizations_organization
            SET plugins_available = COALESCE(
                (
                    SELECT string_agg(match[1], ',')
                    FROM regexp_matches(plugins_available, '([a-zA-Z][a-zA-Z0-9_]+)', 'g') AS match
                ),
                ''
            )
        """)


def noop(_apps, _schema_editor):  # noqa: ARG001
    """No-op reverse migration."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0002_alter_organization_name"),
    ]

    operations = [
        migrations.RunPython(clean_plugins_data, noop),
    ]
