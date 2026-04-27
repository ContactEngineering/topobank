# Stub migration replacing the real 0003 migration which is not needed for mock organizations

from django.db import migrations


class Migration(migrations.Migration):

    replaces = [("organizations", "0003_prepare_plugins_available_data")]

    dependencies = [
        ("organizations", "0002_alter_organization_name"),
    ]

    operations = []
