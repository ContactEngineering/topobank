"""Remove duplicate `Version` rows and enforce uniqueness including NULLs.

`Version` had `unique_together = (("dependency", "major", "minor", "micro",
"extra"),)`, but `micro` and `extra` are nullable and are NULL for most
releases. PostgreSQL treats NULLs as distinct in a UNIQUE constraint, so the
constraint never fired for the common case and concurrent
`Version.objects.get_or_create()` calls (one per tracked dependency, on every
analysis) could insert duplicates.

Once duplicated, the `get()` inside `get_or_create()` raises
`MultipleObjectsReturned` and *every* analysis fails until the rows are cleaned
up. This migration merges the duplicates and replaces the constraint with one
that compares NULLs as equal.
"""

from django.db import migrations, models


def dedupe_versions(apps, schema_editor):
    Version = apps.get_model("taskapp", "Version")
    Configuration = apps.get_model("taskapp", "Configuration")
    Through = Configuration.versions.through

    # Keep the oldest row of each duplicate group so that existing references
    # point at the survivor whenever possible.
    keep_by_key = {}
    duplicates = {}  # duplicate id -> id of the row it is merged into
    for version_id, dependency_id, major, minor, micro, extra in (
        Version.objects.order_by("id").values_list(
            "id", "dependency_id", "major", "minor", "micro", "extra"
        )
    ):
        key = (dependency_id, major, minor, micro, extra)
        if key in keep_by_key:
            duplicates[version_id] = keep_by_key[key]
        else:
            keep_by_key[key] = version_id

    if not duplicates:
        return

    # Repoint Configuration.versions at the surviving rows. Deleting the
    # duplicates directly would cascade away these links and silently strip
    # dependencies from historical configurations.
    for duplicate_id, keep_id in duplicates.items():
        for link_id, configuration_id in Through.objects.filter(
            version_id=duplicate_id
        ).values_list("id", "configuration_id"):
            if Through.objects.filter(
                configuration_id=configuration_id, version_id=keep_id
            ).exists():
                # The configuration already references the survivor; the link
                # via the duplicate is redundant.
                Through.objects.filter(id=link_id).delete()
            else:
                Through.objects.filter(id=link_id).update(version_id=keep_id)

    Version.objects.filter(id__in=list(duplicates)).delete()

    if schema_editor.connection.vendor == "postgresql":
        # Django declares foreign keys DEFERRABLE INITIALLY DEFERRED, so the
        # writes above leave trigger events queued and PostgreSQL then refuses
        # to ALTER TABLE ("pending trigger events"). Force the checks to happen
        # now so that AddConstraint can run in this same transaction -- keeping
        # both in one transaction is what guarantees there is no window in
        # which a concurrent worker could insert a fresh duplicate between the
        # de-duplication and the constraint taking effect.
        schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")


class Migration(migrations.Migration):

    dependencies = [
        ("taskapp", "0002_alter_configuration_table_alter_dependency_table_and_more"),
    ]

    operations = [
        # Drop the old constraint first: the de-duplication below has to run
        # before the stricter constraint is added, and the two cannot coexist.
        migrations.AlterUniqueTogether(
            name="version",
            unique_together=set(),
        ),
        migrations.RunPython(dedupe_versions, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="version",
            constraint=models.UniqueConstraint(
                fields=["dependency", "major", "minor", "micro", "extra"],
                name="unique_version_per_dependency",
                nulls_distinct=False,
            ),
        ),
    ]
