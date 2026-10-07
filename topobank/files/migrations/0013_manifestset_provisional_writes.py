from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("files", "0012_manifest_manifest_unconfirmed_att_idx"),
    ]

    operations = [
        migrations.AddField(
            model_name="manifestset",
            name="provisional_writes",
            field=models.BooleanField(default=False),
        ),
    ]
