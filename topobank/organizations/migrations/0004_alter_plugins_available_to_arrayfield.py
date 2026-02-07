# Generated manually for plugins_available field type change - Part 2: Schema change

from django.contrib.postgres.fields import ArrayField
from django.db import migrations, models

from topobank.organizations.models import get_plugin_choices


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0003_prepare_plugins_available_data"),
    ]

    operations = [
        # Convert clean CSV text to PostgreSQL array
        migrations.RunSQL(
            sql="""
                ALTER TABLE organizations_organization
                ALTER COLUMN plugins_available TYPE text[]
                USING CASE
                    WHEN plugins_available IS NULL OR plugins_available = ''
                    THEN '{}'::text[]
                    ELSE string_to_array(plugins_available, ',')
                END;
            """,
            reverse_sql="""
                ALTER TABLE organizations_organization
                ALTER COLUMN plugins_available TYPE varchar(255)
                USING COALESCE(array_to_string(plugins_available, ','), '');
            """,
        ),
        # Update Django's state to reflect the new field type
        migrations.AlterField(
            model_name="organization",
            name="plugins_available",
            field=ArrayField(
                models.CharField(max_length=100, choices=get_plugin_choices),
                blank=True,
                default=list,
                verbose_name="Available Plugins",
                help_text="Select from available plugin packages for this organization.",
            ),
        ),
    ]
