# Generated manually for plugins_available field type change - Part 2: Schema change with choices

from django.contrib.postgres.fields import ArrayField
from django.db import migrations, models

from topobank.organizations.models import get_plugin_choices


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0003_prepare_plugins_available_data"),
    ]

    operations = [
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
