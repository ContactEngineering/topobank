# Generated manually for plugins_available field type change - Part 1: Data conversion

from django.db import migrations


def convert_csv_to_array_format(_apps, _schema_editor):  # noqa: ARG001
    """Convert comma-separated string values to PostgreSQL array literal format."""
    from django.db import connection

    with connection.cursor() as cursor:
        # Convert CSV strings to PostgreSQL array format: "a,b,c" -> "{a,b,c}"
        # This query:
        # 1. Splits on comma
        # 2. Trims whitespace from each element
        # 3. Filters empty strings
        # 4. Builds PostgreSQL array literal format
        cursor.execute("""
            UPDATE organizations_organization
            SET plugins_available =
                CASE
                    WHEN plugins_available = '' THEN '{}'
                    ELSE
                        '{' ||
                        array_to_string(
                            ARRAY(
                                SELECT trim(elem)
                                FROM unnest(string_to_array(plugins_available, ',')) AS elem
                                WHERE trim(elem) != ''
                            ),
                            ','
                        ) ||
                        '}'
                END
        """)


def convert_array_format_to_csv(_apps, _schema_editor):  # noqa: ARG001
    """Reverse migration: Convert PostgreSQL array format back to CSV strings."""
    from django.db import connection

    with connection.cursor() as cursor:
        # Strip the { } braces to convert back to CSV
        cursor.execute("""
            UPDATE organizations_organization
            SET plugins_available =
                CASE
                    WHEN plugins_available = '{}' THEN ''
                    ELSE trim(both '{}' from plugins_available)
                END
        """)


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0002_alter_organization_name"),
    ]

    operations = [
        migrations.RunPython(convert_csv_to_array_format, convert_array_format_to_csv),
    ]
