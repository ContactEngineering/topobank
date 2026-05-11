# Stub migration to satisfy dependency from other apps

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0004_stub"),
    ]

    operations = []
