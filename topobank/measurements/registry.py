"""
Registry for measurement types.

A measurement type owns everything that depends on *what kind of measurement* is
being handled: how the data file is read into an in-memory data object, which
channels it can import, and which derived artifacts (thumbnails, Deep Zoom
images, canonical files) exist for it.

Types are registered under a stable string key which is also stored in
``Measurement.kind``. Because that key ends up in the database, in exported
containers and in published datasets, it must never be renamed once released.

Built-in types are registered when :mod:`topobank.measurements.types` is imported
(see :class:`topobank.measurements.apps.MeasurementsAppConfig`). External packages
can register their own types either from the ``ready()`` method of their own
``AppConfig`` or through the ``topobank.measurement_types`` entry-point group.
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
    """
    No measurement type is registered for the requested kind.

    This is what surfaces when a measurement was created by a plugin that is no
    longer installed. Such measurements stay listable, downloadable and
    deletable; only reading their data is blocked.
    """

    def __init__(self, name):
        self._name = name

    def __str__(self):
        return (
            f"No measurement type is registered for kind '{self._name}'. The "
            "package providing this kind of measurement may not be installed."
        )


class UnsupportedChannelError(MeasurementRegistryError):
    """No registered measurement type can import this data channel."""


#
# Registry
#

_measurement_types = {}


def register_measurement_type(cls):
    """
    Register a measurement type.

    Can be used as a class decorator. The class is instantiated once (without
    arguments) and that singleton is what :func:`get_measurement_type` returns;
    the class itself is returned so it stays usable under its own name.

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
        If a different type is already registered under the same name.
    """
    name = getattr(cls.Meta, "name", None)
    if not name:
        raise MeasurementRegistryError(
            f"Measurement type '{cls.__name__}' does not declare a `Meta.name`."
        )
    if name in _measurement_types:
        if type(_measurement_types[name]) is cls:
            # Registering the very same class twice is harmless and happens when a
            # module is imported through two different paths.
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
        The registered singleton.

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
    """Return the kinds of all registered measurement types."""
    return list(_measurement_types)


def unregister_measurement_type(name):
    """
    Remove a measurement type from the registry.

    For tests that need to simulate an uninstalled plugin; not part of the normal
    plugin lifecycle.
    """
    _measurement_types.pop(name, None)


def infer_kind(channel):
    """
    Return the kind a data channel is imported as.

    Each registered type decides for itself whether it can import a channel, so
    a type for a new modality does not require changes here.

    Parameters
    ----------
    channel : SurfaceTopography.IO.ChannelInfo
        A channel of an opened data file.

    Returns
    -------
    str
        Kind of the first registered type that claims the channel.

    Raises
    ------
    UnsupportedChannelError
        If no registered type can import it.
    """
    for name, measurement_type in _measurement_types.items():
        if measurement_type.claims_channel(channel):
            return name
    raise UnsupportedChannelError(
        f"None of the registered measurement types "
        f"({', '.join(_measurement_types) or 'none are registered'}) can import "
        f"channel '{getattr(channel, 'name', channel)}'."
    )


def load_entry_points():
    """
    Discover and register measurement types provided by external packages.

    Every entry point in the ``topobank.measurement_types`` group is loaded. An
    entry point may resolve either to a ``MeasurementType`` subclass, which is
    registered, or to a module, which is expected to register its own types on
    import. Failures are logged and skipped: a broken third-party plugin must not
    stop the site from starting.
    """
    from importlib.metadata import entry_points

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
        # If the entry point resolved to a module, importing it was the point: the
        # module is expected to have registered its types itself.
