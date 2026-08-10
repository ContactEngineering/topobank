"""
Registry for measurement types.

A measurement type binds together the three things that make up one kind of
measurement:

* the pydantic schemas that validate its metadata and its file-derived cache,
* the code that reads the underlying data file into an in-memory data object,
* the code that derives cached artifacts (thumbnails, canonical files, ...).

Types are registered under a stable string key which is also stored in
``Measurement.kind``. Because that key ends up in the database, in exported
containers and in published datasets, it must never be renamed once released.

Built-in types are registered when :mod:`topobank.measurements.types` is
imported (see :class:`topobank.measurements.apps.MeasurementsAppConfig`).
External packages can register their own types either from the ``ready()``
method of their own ``AppConfig`` or through the ``topobank.measurement_types``
entry-point group.
"""

import logging

_log = logging.getLogger(__name__)

#: Name of the entry-point group used to discover measurement types shipped by
#: external packages.
ENTRY_POINT_GROUP = "topobank.measurement_types"


#
# Exceptions
#


class MeasurementRegistryError(Exception):
    """Generic problem while handling measurement types."""


class AlreadyRegisteredError(MeasurementRegistryError):
    """A measurement type has already been registered for the given key."""

    def __init__(self, name):
        self._name = name

    def __str__(self):
        return f"A measurement type for kind '{self._name}' is already registered."


class MeasurementNotInspectedError(MeasurementRegistryError):
    """
    The kind of a measurement is not known yet.

    Raised for a measurement whose data file has not been inspected, so no
    measurement type can be determined for it.
    """


class UnknownMeasurementKindError(MeasurementRegistryError):
    """No measurement type is registered for the requested kind.

    This is the error that surfaces when a measurement was created by a plugin
    that is no longer installed. Such measurements remain listable, downloadable
    and deletable; only reading their data and editing their metadata is
    blocked.
    """

    def __init__(self, name):
        self._name = name

    def __str__(self):
        return (
            f"No measurement type is registered for kind '{self._name}'. The "
            "package providing this kind of measurement may not be installed."
        )


#
# Registry
#

_measurement_types = {}


def register_measurement_type(cls):
    """
    Register a measurement type.

    Can be used as a class decorator. The class is instantiated once (without
    arguments) and the resulting singleton is what :func:`get_measurement_type`
    returns; the class itself is returned so that it stays usable under its own
    name.

    Parameters
    ----------
    cls : type
        Subclass of :class:`topobank.measurements.types.MeasurementType`.

    Returns
    -------
    type
        The class that was passed in.

    Raises
    ------
    MeasurementRegistryError
        If the class does not declare a name.
    AlreadyRegisteredError
        If another type is already registered under the same name.
    """
    name = getattr(cls.Meta, "name", None)
    if not name:
        raise MeasurementRegistryError(
            f"Measurement type '{cls.__name__}' does not declare a `Meta.name`."
        )
    if name in _measurement_types:
        existing = type(_measurement_types[name])
        if existing is cls:
            # Registering the very same class twice is harmless and can happen
            # when a module is imported through two different paths.
            return cls
        raise AlreadyRegisteredError(name)
    _measurement_types[name] = cls()
    _log.debug("Registered measurement type '%s' (%s).", name, cls.__name__)
    return cls


def get_measurement_type(name):
    """
    Return the measurement type registered for `name`.

    Parameters
    ----------
    name : str
        Registry key, i.e. the value of ``Measurement.kind``.

    Returns
    -------
    MeasurementType
        The registered singleton instance.

    Raises
    ------
    UnknownMeasurementKindError
        If nothing is registered under this key.
    """
    try:
        return _measurement_types[name]
    except KeyError:
        raise UnknownMeasurementKindError(name)


def has_measurement_type(name):
    """Return True if a measurement type is registered for `name`."""
    return name in _measurement_types


def get_measurement_types():
    """Return all registered measurement types, keyed by kind."""
    return dict(_measurement_types)


def get_measurement_kinds():
    """Return the names (kinds) of all registered measurement types."""
    return list(_measurement_types.keys())


def unregister_measurement_type(name):
    """
    Remove a measurement type from the registry.

    This exists for tests that need to simulate an uninstalled plugin; it is not
    part of the normal plugin lifecycle.
    """
    _measurement_types.pop(name, None)


def sniff_measurement_file(measurement):
    """
    Open a measurement's data file using whichever registered type can read it.

    Measurement types that share a file format share their ``sniff``
    implementation, so each distinct implementation is tried only once and the
    file is opened only once.

    Parameters
    ----------
    measurement : Measurement
        The measurement whose data file should be opened.

    Returns
    -------
    FileInspection
        The opened file and its channel inventory.

    Raises
    ------
    UnsupportedFileError
        If no registered measurement type can read the file.
    """
    from .types import UnsupportedFileError

    tried = set()
    for measurement_type in _measurement_types.values():
        sniff = type(measurement_type).sniff
        # Unwrap the classmethod so that types inheriting one implementation are
        # recognized as sharing it.
        key = getattr(sniff, "__func__", sniff)
        if key in tried:
            continue
        tried.add(key)
        inspection = measurement_type.sniff(measurement)
        if inspection is not None:
            return inspection
    raise UnsupportedFileError(
        f"None of the registered measurement types ({', '.join(_measurement_types)}) "
        f"can read the data file of measurement {measurement.id}."
    )


def load_entry_points():
    """
    Discover and register measurement types provided by external packages.

    Every entry point in the ``topobank.measurement_types`` group is loaded. An
    entry point may resolve either to a ``MeasurementType`` subclass (which is
    registered) or to a module (which is expected to register its types itself
    on import). Failures are logged and skipped: a broken third-party plugin
    must not prevent the site from starting.
    """
    try:
        from importlib.metadata import entry_points
    except ImportError:  # pragma: no cover - Python < 3.8
        return

    for entry_point in entry_points(group=ENTRY_POINT_GROUP):
        try:
            obj = entry_point.load()
        except Exception:
            _log.exception(
                "Failed to load measurement type from entry point '%s'.",
                entry_point.name,
            )
            continue
        if isinstance(obj, type):
            try:
                register_measurement_type(obj)
            except MeasurementRegistryError:
                _log.exception(
                    "Failed to register measurement type '%s' from entry point.",
                    entry_point.name,
                )
        # If the entry point resolved to a module, importing it was the point:
        # the module is expected to have registered its types itself.
