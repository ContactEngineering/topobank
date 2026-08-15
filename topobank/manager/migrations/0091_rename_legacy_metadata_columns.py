"""
Rename the metadata columns to `legacy_*`.

`0090` copied their contents into `metadata` and `file_info`, which are now the
only things read. The columns are kept so that a backfill found to be wrong can
be re-run from the original data, but keeping them under their old names means a
reader nobody noticed goes on working and quietly returns pre-migration values.
Renaming turns that silent staleness into an `AttributeError`.

`0092` drops them once the backfill has been seen to be right on real data.

A rename rather than a copy: this is a catalogue change, so it does not rewrite
the table.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("manager", "0090_backfill_measurement_metadata"),
    ]

    operations = [
        migrations.RenameField(
            model_name="measurement",
            old_name="size_x",
            new_name="legacy_size_x",
        ),
        migrations.RenameField(
            model_name="measurement",
            old_name="size_y",
            new_name="legacy_size_y",
        ),
        migrations.RenameField(
            model_name="measurement",
            old_name="unit",
            new_name="legacy_unit",
        ),
        migrations.RenameField(
            model_name="measurement",
            old_name="height_scale",
            new_name="legacy_height_scale",
        ),
        migrations.RenameField(
            model_name="measurement",
            old_name="detrend_mode",
            new_name="legacy_detrend_mode",
        ),
        migrations.RenameField(
            model_name="measurement",
            old_name="is_periodic",
            new_name="legacy_is_periodic",
        ),
        migrations.RenameField(
            model_name="measurement",
            old_name="fill_undefined_data_mode",
            new_name="legacy_fill_undefined_data_mode",
        ),
        migrations.RenameField(
            model_name="measurement",
            old_name="instrument_name",
            new_name="legacy_instrument_name",
        ),
        migrations.RenameField(
            model_name="measurement",
            old_name="instrument_type",
            new_name="legacy_instrument_type",
        ),
        migrations.RenameField(
            model_name="measurement",
            old_name="instrument_parameters",
            new_name="legacy_instrument_parameters",
        ),
        migrations.RenameField(
            model_name="measurement",
            old_name="size_editable",
            new_name="legacy_size_editable",
        ),
        migrations.RenameField(
            model_name="measurement",
            old_name="unit_editable",
            new_name="legacy_unit_editable",
        ),
        migrations.RenameField(
            model_name="measurement",
            old_name="height_scale_editable",
            new_name="legacy_height_scale_editable",
        ),
        migrations.RenameField(
            model_name="measurement",
            old_name="is_periodic_editable",
            new_name="legacy_is_periodic_editable",
        ),
        migrations.RenameField(
            model_name="measurement",
            old_name="has_undefined_data",
            new_name="legacy_has_undefined_data",
        ),
        migrations.RenameField(
            model_name="measurement",
            old_name="undefined_data_fraction",
            new_name="legacy_undefined_data_fraction",
        ),
        migrations.RenameField(
            model_name="measurement",
            old_name="detrend_parameters",
            new_name="legacy_detrend_parameters",
        ),
        migrations.RenameField(
            model_name="measurement",
            old_name="resolution_x",
            new_name="legacy_resolution_x",
        ),
        migrations.RenameField(
            model_name="measurement",
            old_name="resolution_y",
            new_name="legacy_resolution_y",
        ),
        migrations.RenameField(
            model_name="measurement",
            old_name="bandwidth_lower",
            new_name="legacy_bandwidth_lower",
        ),
        migrations.RenameField(
            model_name="measurement",
            old_name="bandwidth_upper",
            new_name="legacy_bandwidth_upper",
        ),
        migrations.RenameField(
            model_name="measurement",
            old_name="short_reliability_cutoff",
            new_name="legacy_short_reliability_cutoff",
        ),
    ]
