"""
Registry for measurement handlers.

A measurement handler owns everything that depends on *what kind of measurement* is
being handled: how the data file is read into an in-memory data object, which
channels it can import, and which derived artifacts (thumbnails, Deep Zoom
images, canonical files) exist for it.

Types are registered under a stable string key which is also stored in
``Measurement.kind``. Because that key ends up in the database, in exported
containers and in published datasets, it must never be renamed once released.

Built-in types are registered when :mod:`topobank.measurements.handlers` is imported
(see :class:`topobank.measurements.apps.MeasurementsAppConfig`). External packages
can register their own types either from the ``ready()`` method of their own
``AppConfig`` or through the ``topobank.measurement_handlers`` entry-point group.
"""

import logging

_log = logging.getLogger(__name__)

#: Name of the entry-point group used to discover measurement handlers shipped by
#: external packages.
ENTRY_POINT_GROUP = "topobank.measurement_handlers"


#
# Exceptions
#


class MeasurementRegistryError(Exception):
    """Generic problem while handling measurement handlers."""


class AlreadyRegisteredError(MeasurementRegistryError):
    """A measurement handler has already been registered for the given key."""

    def __init__(self, name):
        self._name = name

    def __str__(self):
        return f"A measurement handler for kind '{self._name}' is already registered."


class MeasurementNotInspectedError(MeasurementRegistryError):
    """
    The kind of a measurement is not known yet.

    Raised for a measurement whose data file has not been inspected, so no
    measurement handler can be determined for it.
    """


class UnknownMeasurementKindError(MeasurementRegistryError):
    """
    No measurement handler is registered for the requested kind.

    This is what surfaces when a measurement was created by a plugin that is no
    longer installed. Such measurements stay listable, downloadable and
    deletable; only reading their data is blocked.
    """

    def __init__(self, name):
        self._name = name

    def __str__(self):
        return (
            f"No measurement handler is registered for kind '{self._name}'. The "
            "package providing this kind of measurement may not be installed."
        )


class UnsupportedChannelError(MeasurementRegistryError):
    """No registered measurement handler can import this data channel."""


#
# Registry
#

_handlers = {}


def register_handler(cls):
    """
    Register a measurement handler.

    Can be used as a class decorator. The class is instantiated once (without
    arguments) and that singleton is what :func:`get_handler` returns;
    the class itself is returned so it stays usable under its own name.

    Parameters
    ----------
    cls : type
        Subclass of :class:`topobank.measurements.handlers.MeasurementHandler`.

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
    kind = getattr(cls.Meta, "kind", None)
    if not kind:
        raise MeasurementRegistryError(
            f"Measurement handler '{cls.__name__}' does not declare a `Meta.kind`."
        )
    if kind in _handlers:
        if type(_handlers[kind]) is cls:
            # Registering the very same class twice is harmless and happens when a
            # module is imported through two different paths.
            return cls
        raise AlreadyRegisteredError(kind)
    _handlers[kind] = cls()
    _log.debug("Registered measurement handler '%s' (%s).", kind, cls.__name__)
    return cls


def get_handler(name):
    """
    Return the handler registered for `kind`.

    Parameters
    ----------
    name : str
        Registry key, i.e. the value of ``Measurement.kind``.

    Returns
    -------
    MeasurementHandler
        The registered singleton.

    Raises
    ------
    UnknownMeasurementKindError
        If nothing is registered under this key.
    """
    try:
        return _handlers[name]
    except KeyError:
        raise UnknownMeasurementKindError(name)


def has_handler(name):
    """Return True if a handler is registered for `kind`."""
    return name in _handlers


def get_handlers():
    """Return all registered handlers, keyed by kind."""
    return dict(_handlers)


def get_kinds():
    """Return the kinds of all registered handlers."""
    return list(_handlers)


def unregister_handler(name):
    """
    Remove a handler from the registry.

    For tests that need to simulate an uninstalled plugin; not part of the normal
    plugin lifecycle.
    """
    _handlers.pop(name, None)


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
    for name, handler in _handlers.items():
        if handler.claims_channel(channel):
            return name
    raise UnsupportedChannelError(
        f"None of the registered measurement handlers "
        f"({', '.join(_handlers) or 'none are registered'}) can import "
        f"channel '{getattr(channel, 'name', channel)}'."
    )


def load_entry_points():
    """
    Discover and register measurement handlers provided by external packages.

    Every entry point in the ``topobank.measurement_handlers`` group is loaded. An
    entry point may resolve either to a ``MeasurementHandler`` subclass, which is
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
                "Failed to load measurement handler from entry point '%s'.",
                entry_point.name,
            )
            continue
        if isinstance(obj, type):
            try:
                register_handler(obj)
            except MeasurementRegistryError:
                _log.exception(
                    "Failed to register measurement handler '%s' from entry point.",
                    entry_point.name,
                )
        # If the entry point resolved to a module, importing it was the point: the
        # module is expected to have registered its types itself.
