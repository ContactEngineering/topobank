# Generated manually for plugins_available field type change - Part 1: Clean data

from django.db import migrations


def clean_plugins_data(_apps, _schema_editor):  # noqa: ARG001
    """
    Extract valid plugin names from potentially corrupted data.

    Handles various corrupted formats:
    - Character-by-character arrays: ["{", "t", "o", "p", ...}]
    - Escaped quotes: "\"{}\"", "\"\\\"{}\\\"\""
    - Normal CSV: "first_plugin,other_plugin"
    - PostgreSQL array literals: "{first_plugin}"

    Uses regex to extract valid identifiers (e.g., first_plugin, topobank_statistics).
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
