# Generated for performance optimization
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('properties', '0002_alter_property_table'),
    ]

    operations = [
        # Add index on surface foreign key for reverse lookups
        migrations.AddIndex(
            model_name='property',
            index=models.Index(fields=['surface'], name='property_surface_idx'),
        ),
        # Add composite index for property lookups by surface and name
        migrations.AddIndex(
            model_name='property',
            index=models.Index(fields=['surface', 'name'], name='property_lookup_idx'),
        ),
    ]
