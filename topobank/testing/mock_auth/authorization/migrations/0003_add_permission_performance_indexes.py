# Stub migration to satisfy dependency from other apps

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("authorization", "0002_organizationpermission"),
    ]

    operations = []
