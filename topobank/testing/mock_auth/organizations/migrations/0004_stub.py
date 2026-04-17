# Stub migration replacing the real 0004 migration which is not needed for mock organizations

from django.db import migrations


class Migration(migrations.Migration):

    replaces = [("organizations", "0004_alter_plugins_available_to_arrayfield")]

    dependencies = [
        ("organizations", "0003_stub"),
    ]

    operations = []
