# Generated manually to fix corrupted plugins_available data

from django.db import migrations


def fix_corrupted_array_data(_apps, _schema_editor):  # noqa: ARG001
    """
    Fix corrupted plugins_available array data.

    The previous migration incorrectly converted data character-by-character,
    resulting in arrays like ["{", "t", "o", "p", "_", "p", "l", "u", "g", "}"].

    This extracts valid plugin names using regex and rebuilds the array.
    Valid plugin names must:
    - Start with a letter
    - Contain only letters, digits, and underscores
    - Be at least 3 characters long (filters out garbage like single chars)
    """
    from django.db import connection

    with connection.cursor() as cursor:
        # Convert array to string, extract valid plugin names, convert back to array
        # The regex requires: starts with letter, 3+ total chars (filters garbage)
        cursor.execute("""
            UPDATE organizations_organization
            SET plugins_available = ARRAY(
                SELECT match[1]
                FROM regexp_matches(
                    array_to_string(plugins_available, ''),
                    '([a-zA-Z][a-zA-Z0-9_]{2,})',
                    'g'
                ) AS match
            )
        """)


def noop(_apps, _schema_editor):  # noqa: ARG001
    """No-op reverse migration."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0004_alter_plugins_available_to_arrayfield"),
    ]

    operations = [
        migrations.RunPython(fix_corrupted_array_data, noop),
    ]
