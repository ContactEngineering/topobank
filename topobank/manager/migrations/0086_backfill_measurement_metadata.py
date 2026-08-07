"""
Backfill `kind`, `metadata`, `file_info` and the channel name of every measurement.

Everything here is derived from columns that are already in the database - no data
file is opened, so this runs without touching object storage.

Kind inference
--------------
A measurement that has been inspected has its resolution and size populated, and
that is enough to tell the three height kinds apart:

* two-dimensional data (``resolution_y`` or ``size_y`` set) is a topography map;
* otherwise, ``is_periodic_editable == False`` marks a nonuniform line scan,
  because that flag was cleared exactly for non-uniform data;
* everything else is a uniform line scan.

Rows that were never inspected (no ``data_source``) keep an empty kind and are
classified by their next ``refresh_cache``, which is authoritative anyway. Because
the inference is a heuristic for already-inspected rows, the management command
``check_measurement_kinds`` reports any row whose stored kind disagrees with a
fresh inspection, so a full re-inspection sweep is only needed if that report
actually finds something.

Channel identity
----------------
``data_source`` was an index into ``channel_names``. The name at that index becomes
``channel_name``; an occurrence ordinal is recorded only where that name occurs
more than once in the list, matching the rule the application uses. Where the
cached channel list is empty or the index is out of range there is no trustworthy
name to preserve, so the row is left for its next inspection.
"""

from django.db import migrations

#: Kinds, spelled out rather than imported: a migration must keep working even if
#: the registry keys are reorganized later.
TOPOGRAPHY_MAP = "topography-map"
UNIFORM_LINE_SCAN = "uniform-line-scan"
NONUNIFORM_LINE_SCAN = "nonuniform-line-scan"

#: Metadata fields per kind, mirroring the pydantic schemas at the time of this
#: migration.
_COMMON_METADATA = ["size_x", "unit", "height_scale", "detrend_mode"]
_METADATA_FIELDS = {
    TOPOGRAPHY_MAP: _COMMON_METADATA + [
        "size_y",
        "is_periodic",
        "fill_undefined_data_mode",
    ],
    UNIFORM_LINE_SCAN: _COMMON_METADATA + [
        "is_periodic",
        "fill_undefined_data_mode",
    ],
    # A nonuniform line scan supports neither periodicity nor interpolation of
    # undefined data, so its schema has no such fields.
    NONUNIFORM_LINE_SCAN: list(_COMMON_METADATA),
}

_COMMON_FILE_INFO = [
    "resolution_x",
    "bandwidth_lower",
    "bandwidth_upper",
    "short_reliability_cutoff",
    "has_undefined_data",
    "undefined_data_fraction",
    "detrend_parameters",
    "size_editable",
    "unit_editable",
    "height_scale_editable",
    "is_periodic_editable",
]
_FILE_INFO_FIELDS = {
    TOPOGRAPHY_MAP: _COMMON_FILE_INFO + ["resolution_y"],
    UNIFORM_LINE_SCAN: list(_COMMON_FILE_INFO),
    NONUNIFORM_LINE_SCAN: list(_COMMON_FILE_INFO),
}

#: Columns restored when the backfill is reversed.
_LEGACY_COLUMNS = sorted(
    set(_COMMON_METADATA)
    | {"size_y", "is_periodic", "fill_undefined_data_mode"}
    | set(_COMMON_FILE_INFO)
    | {"resolution_y"}
)

#
# Normalization of values that the old columns did not actually constrain.
#
# `unit`, `detrend_mode`, `fill_undefined_data_mode` and `instrument_type` were
# `TextField`s with `choices`, which Django enforces in forms but not in the
# database, and `full_clean` was never called on save. Rows can therefore hold
# values outside those lists - "um" instead of "µm", or the empty instrument type
# that the container importer used to write. The new schemas *do* constrain these,
# so anything not normalized here would make the metadata unparseable. The
# accepted values are spelled out rather than imported: a migration has to keep
# behaving the same way even after the schemas move on.
#
_VALID_UNITS = {"km", "m", "mm", "µm", "nm", "Å", "pm"}
_UNIT_ALIASES = {
    "um": "µm",
    "μm": "µm",  # U+03BC greek small letter mu, vs. U+00B5 micro sign
    "micron": "µm",
    "microns": "µm",
    "micrometer": "µm",
    "micrometers": "µm",
    "nanometer": "nm",
    "nanometers": "nm",
    "millimeter": "mm",
    "millimeters": "mm",
    "meter": "m",
    "meters": "m",
    "kilometer": "km",
    "kilometers": "km",
    "picometer": "pm",
    "picometers": "pm",
    "a": "Å",
    "ang": "Å",
    "angstrom": "Å",
    "angstroms": "Å",
    "Å": "Å",
    "Å": "Å",  # angstrom sign
}
_VALID_DETREND_MODES = {"center", "height", "curvature"}
_VALID_FILL_MODES = {"do-not-fill", "harmonic"}
_VALID_INSTRUMENT_TYPES = {"undefined", "microscope-based", "contact-based"}


def normalize_unit(unit):
    """
    Map a stored unit onto one the schema accepts.

    Returns ``(unit, ok)``. A unit that cannot be mapped becomes ``None`` rather
    than being stored as-is: that leaves the measurement with incomplete metadata,
    which the UI reports and which the next inspection repairs from the data file
    for the (large) majority of formats that state their own unit. Storing the
    unrecognized value instead would make the metadata fail validation, and the
    measurement could not even be displayed.
    """
    if unit is None:
        return None, True
    if unit in _VALID_UNITS:
        return unit, True
    alias = _UNIT_ALIASES.get(unit) or _UNIT_ALIASES.get(unit.strip().lower())
    if alias is not None:
        return alias, True
    return None, False


def normalize_choice(value, valid, default):
    """Return ``(value, ok)``, falling back to `default` for unknown values."""
    if value in valid:
        return value, True
    return default, False


def infer_kind(measurement):
    """Return the kind of an already-inspected measurement, or "" if unknown."""
    if measurement.data_source is None:
        # Never inspected; the next `refresh_cache` determines the kind from the
        # data file itself.
        return ""
    if measurement.resolution_y is not None or measurement.size_y is not None:
        return TOPOGRAPHY_MAP
    if not measurement.is_periodic_editable:
        return NONUNIFORM_LINE_SCAN
    return UNIFORM_LINE_SCAN


def channel_identity(measurement):
    """
    Translate the stored channel index into a name and an occurrence ordinal.

    Returns
    -------
    tuple
        ``(name, occurrence, index_hint)``. The name is None when the cached
        channel list cannot provide one, in which case the index is kept as a
        hint for the next inspection.
    """
    index = measurement.data_source
    if index is None:
        return None, None, None

    # `channel_names` holds [name, unit] pairs.
    names = []
    for entry in measurement.channel_names or []:
        if isinstance(entry, (list, tuple)) and entry:
            names.append(entry[0])
        elif isinstance(entry, str):
            names.append(entry)
        else:
            names.append(None)

    if not (0 <= index < len(names)) or names[index] is None:
        # No trustworthy name: let the next inspection resolve the index.
        return None, None, index

    name = names[index]
    same_name = [i for i, other in enumerate(names) if other == name]
    # Only ambiguous names get an ordinal; a NULL asserts the name was unique.
    occurrence = same_name.index(index) if len(same_name) > 1 else None
    return name, occurrence, None


def backfill(apps, schema_editor):
    Measurement = apps.get_model("manager", "Measurement")

    updated = 0
    # Rows whose stored values had to be corrected. Reported at the end so that an
    # operator can follow up; none of it is fatal.
    bad_units = []
    bad_modes = []
    for measurement in Measurement.objects.all().iterator(chunk_size=500):
        kind = infer_kind(measurement)
        name, occurrence, index_hint = channel_identity(measurement)

        measurement.kind = kind
        measurement.channel_name = name
        measurement.channel_occurrence = occurrence
        measurement.channel_index_hint = index_hint

        if kind:
            metadata = {"kind": kind}
            for field in _METADATA_FIELDS[kind]:
                metadata[field] = getattr(measurement, field)

            unit, ok = normalize_unit(metadata.get("unit"))
            metadata["unit"] = unit
            if not ok:
                bad_units.append((measurement.pk, getattr(measurement, "unit")))

            metadata["detrend_mode"], ok = normalize_choice(
                metadata.get("detrend_mode"), _VALID_DETREND_MODES, "center"
            )
            if not ok:
                bad_modes.append(
                    (measurement.pk, "detrend_mode", measurement.detrend_mode)
                )
            if "fill_undefined_data_mode" in metadata:
                metadata["fill_undefined_data_mode"], ok = normalize_choice(
                    metadata.get("fill_undefined_data_mode"),
                    _VALID_FILL_MODES,
                    "do-not-fill",
                )
                if not ok:
                    bad_modes.append(
                        (
                            measurement.pk,
                            "fill_undefined_data_mode",
                            measurement.fill_undefined_data_mode,
                        )
                    )

            # The container importer used to write an empty instrument type.
            instrument_type, ok = normalize_choice(
                measurement.instrument_type, _VALID_INSTRUMENT_TYPES, "undefined"
            )
            if not ok and measurement.instrument_type:
                bad_modes.append(
                    (measurement.pk, "instrument_type", measurement.instrument_type)
                )
            # Null-valued instrument parameters are dropped: the upstream
            # `InstrumentParametersModel` declares its fields as non-optional with
            # a None default, so it accepts a missing key but rejects an explicit
            # null, and metadata containing one could not be read back.
            parameters = {
                key: value
                for key, value in (measurement.instrument_parameters or {}).items()
                if value is not None
            }
            metadata["instrument"] = {
                "name": measurement.instrument_name or "",
                "type": instrument_type,
                "parameters": parameters,
            }
            # `height_scale` was non-nullable with a default of 1, but be explicit:
            # the schema requires a number.
            if metadata.get("height_scale") is None:
                metadata["height_scale"] = 1.0

            file_info = {"kind": kind, "channels": []}
            for field in _FILE_INFO_FIELDS[kind]:
                file_info[field] = getattr(measurement, field)
            # The channel inventory needs the data file, so it stays empty until
            # the next inspection. The name recorded above is what identifies the
            # channel; this list only feeds the selection UI.
        else:
            # Not inspected yet: nothing to describe. `metadata` is deliberately
            # left empty so that the first inspection still imports the optional
            # metadata (acquisition date, instrument) from the data file.
            metadata = {}
            file_info = {}

        measurement.metadata = metadata
        measurement.file_info = file_info
        measurement.save(
            update_fields=[
                "kind",
                "metadata",
                "file_info",
                "channel_name",
                "channel_occurrence",
                "channel_index_hint",
            ]
        )
        updated += 1

    if updated:
        print(f"  Backfilled metadata of {updated} measurement(s).")
    if bad_units:
        print(
            f"  WARNING: {len(bad_units)} measurement(s) had a unit that is not a "
            "recognized length unit. Their unit has been cleared, so they now count "
            "as having incomplete metadata; re-inspecting them recovers the unit "
            "from the data file wherever the file states it."
        )
        for pk, value in bad_units[:20]:
            print(f"    measurement {pk}: {value!r}")
        if len(bad_units) > 20:
            print(f"    ... and {len(bad_units) - 20} more")
    if bad_modes:
        print(
            f"  WARNING: {len(bad_modes)} stored value(s) were outside the allowed "
            "set and have been reset to the default:"
        )
        for pk, field, value in bad_modes[:20]:
            print(f"    measurement {pk}: {field}={value!r}")
        if len(bad_modes) > 20:
            print(f"    ... and {len(bad_modes) - 20} more")


def restore(apps, schema_editor):
    """
    Copy the metadata back into the legacy columns.

    Needed so that this migration can be reversed while the columns still exist,
    i.e. before 0085 has run.
    """
    Measurement = apps.get_model("manager", "Measurement")

    for measurement in Measurement.objects.exclude(kind="").iterator(chunk_size=500):
        metadata = measurement.metadata or {}
        file_info = measurement.file_info or {}
        for column in _LEGACY_COLUMNS:
            if column in metadata:
                setattr(measurement, column, metadata[column])
            elif column in file_info:
                setattr(measurement, column, file_info[column])
        instrument = metadata.get("instrument") or {}
        measurement.instrument_name = instrument.get("name", "")
        measurement.instrument_type = instrument.get("type", "undefined")
        measurement.instrument_parameters = instrument.get("parameters", {})
        measurement.save()


class Migration(migrations.Migration):

    dependencies = [
        ("manager", "0085_measurement_metadata_fields"),
    ]

    operations = [
        migrations.RunPython(backfill, restore),
    ]
