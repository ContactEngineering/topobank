"""
Registry for measurement adapters.

A measurement adapter owns everything that depends on *what kind of measurement* is
being handled: how the data file is read into an in-memory data object, which
channels it can import, and which derived artifacts (thumbnails, Deep Zoom
images, canonical files) exist for it.

Types are registered under a stable string key which is also stored in
``Measurement.kind``. Because that key ends up in the database, in exported
containers and in published datasets, it must never be renamed once released.

Built-in types are registered when :mod:`topobank.measurements.adapters` is imported
(see :class:`topobank.measurements.apps.MeasurementsAppConfig`). External packages
can register their own types either from the ``ready()`` method of their own
``AppConfig`` or through the ``topobank.measurement_adapters`` entry-point group.
"""

import logging

_log = logging.getLogger(__name__)

#: Name of the entry-point group used to discover measurement adapters shipped by
#: external packages.
ENTRY_POINT_GROUP = "topobank.measurement_adapters"


#
# Exceptions
#


class MeasurementRegistryError(Exception):
    """Generic problem while handling measurement adapters."""


class AlreadyRegisteredError(MeasurementRegistryError):
    """A measurement adapter has already been registered for the given key."""

    def __init__(self, name):
        self._name = name

    def __str__(self):
        return f"A measurement adapter for kind '{self._name}' is already registered."


class MeasurementNotInspectedError(MeasurementRegistryError):
    """
    The kind of a measurement is not known yet.

    Raised for a measurement whose data file has not been inspected, so no
    measurement adapter can be determined for it.
    """


class UnknownMeasurementKindError(MeasurementRegistryError):
    """
    No measurement adapter is registered for the requested kind.

    This is what surfaces when a measurement was created by a plugin that is no
    longer installed. Such measurements stay listable, downloadable and
    deletable; only reading their data is blocked.
    """

    def __init__(self, name):
        self._name = name

    def __str__(self):
        return (
            f"No measurement adapter is registered for kind '{self._name}'. The "
            "package providing this kind of measurement may not be installed."
        )


class UnsupportedChannelError(MeasurementRegistryError):
    """No registered measurement adapter can import this data channel."""


#
# Registry
#

_adapters = {}


def register_adapter(cls):
    """
    Register a measurement adapter.

    Can be used as a class decorator. The class is instantiated once (without
    arguments) and that singleton is what :func:`get_adapter` returns;
    the class itself is returned so it stays usable under its own name.

    Parameters
    ----------
    cls : type
        Subclass of :class:`topobank.measurements.adapters.MeasurementAdapter`.

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
    # `Meta.name` is the kind, matching how the workflow registry in `analysis`
    # names its own key.
    kind = getattr(cls.Meta, "name", None)
    if not kind:
        raise MeasurementRegistryError(
            f"Measurement adapter '{cls.__name__}' does not declare a `Meta.name`."
        )
    if kind in _adapters:
        if type(_adapters[kind]) is cls:
            # Registering the very same class twice is harmless and happens when a
            # module is imported through two different paths.
            return cls
        raise AlreadyRegisteredError(kind)
    _adapters[kind] = cls()
    _log.debug("Registered measurement adapter '%s' (%s).", kind, cls.__name__)
    return cls


def get_adapter(name):
    """
    Return the adapter registered for `kind`.

    Parameters
    ----------
    name : str
        Registry key, i.e. the value of ``Measurement.kind``.

    Returns
    -------
    MeasurementAdapter
        The registered singleton.

    Raises
    ------
    UnknownMeasurementKindError
        If nothing is registered under this key.
    """
    try:
        return _adapters[name]
    except KeyError:
        raise UnknownMeasurementKindError(name)


def has_adapter(name):
    """Return True if a adapter is registered for `kind`."""
    return name in _adapters


def get_adapters():
    """Return all registered adapters, keyed by kind."""
    return dict(_adapters)


def get_kinds():
    """Return the kinds of all registered adapters."""
    return list(_adapters)


def unregister_adapter(name):
    """
    Remove a adapter from the registry.

    For tests that need to simulate an uninstalled plugin; not part of the normal
    plugin lifecycle.
    """
    _adapters.pop(name, None)


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
    for name, adapter in _adapters.items():
        if adapter.claims_channel(channel):
            return name
    raise UnsupportedChannelError(
        f"None of the registered measurement adapters "
        f"({', '.join(_adapters) or 'none are registered'}) can import "
        f"channel '{getattr(channel, 'name', channel)}'."
    )


def load_entry_points():
    """
    Discover and register measurement adapters provided by external packages.

    Every entry point in the ``topobank.measurement_adapters`` group is loaded. An
    entry point may resolve either to a ``MeasurementAdapter`` subclass, which is
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
                "Failed to load measurement adapter from entry point '%s'.",
                entry_point.name,
            )
            continue
        if isinstance(obj, type):
            try:
                register_adapter(obj)
            except MeasurementRegistryError:
                _log.exception(
                    "Failed to register measurement adapter '%s' from entry point.",
                    entry_point.name,
                )
        # If the entry point resolved to a module, importing it was the point: the
        # module is expected to have registered its types itself.
