"""Kinds of measurement, and the adapter that handles each.

A measurement adapter owns everything that depends on *what kind of measurement*
is being handled: which channels of a data file it can import, which fields an
inspection reads from such a channel, how the data is read, and how its derived
files are rendered (a thumbnail of a map is an image, of a line scan a plot; only a
map has deep zoom images).

Which derived files a deployment generates is a separate question, answered by the
processing steps (`topobank.manager.steps`). A step asks the adapter of the
measurement whether it applies (`has_deepzoom`) and lets the adapter render
whatever depends on the kind.

The three built-in kinds are backed by ``SurfaceTopography`` and share
`SurfaceTopographyAdapter`. A kind for an entirely different modality subclasses
`MeasurementAdapter` and registers itself with `register_adapter`.

Like `topobank.manager.processing`, this module imports neither Django nor any
model, so the processing can run outside the Django process (see
``TOPOBANK_PROCESSING_BACKEND``). Adapters therefore never see a model instance:
they work on reader channels, the in-memory data object and the
`InspectionParameters` of the measurement.

Ported from the measurement adapters of topobank's ``26_measurement_model``
branch, without that branch's JSON metadata documents: the fields stay columns of
`Topography`.
"""

import abc
import io
import logging

import matplotlib
import numpy as np
import PIL
from matplotlib.figure import Figure

_log = logging.getLogger(__name__)

#: Format of the canonical ("squeezed") representation of height data
CANONICAL_DATAFILE_FORMAT = "nc"


#
# Exceptions
#


class MeasurementRegistryError(Exception):
    """Generic problem while handling measurement adapters."""


class AlreadyRegisteredError(MeasurementRegistryError):
    """A different adapter is already registered for the kind."""

    def __init__(self, name):
        self._name = name

    def __str__(self):
        return f"A measurement adapter for kind '{self._name}' is already registered."


class UnknownMeasurementKindError(MeasurementRegistryError):
    """No adapter is registered for the kind.

    What a measurement created by a plugin that is no longer installed runs into.
    """

    def __init__(self, name):
        self._name = name

    def __str__(self):
        return (
            f"No measurement adapter is registered for kind '{self._name}'. The "
            "package providing this kind of measurement may not be installed."
        )


class UnsupportedChannelError(MeasurementRegistryError):
    """No registered adapter can import the data channel."""


#
# Registry
#

_adapters = {}


def register_adapter(cls):
    """Register a measurement adapter (usable as a class decorator).

    The class is instantiated once; that singleton is what `get_adapter` returns.
    Its `Meta.name` is the kind, which is stored in `Topography.kind` and must
    therefore never be renamed once released.
    """
    kind = getattr(cls.Meta, "name", None)
    if not kind:
        raise MeasurementRegistryError(
            f"Measurement adapter '{cls.__name__}' does not declare a `Meta.name`."
        )
    if kind in _adapters:
        if type(_adapters[kind]) is cls:
            # The same class imported through two paths
            return cls
        raise AlreadyRegisteredError(kind)
    _adapters[kind] = cls()
    _log.debug("Registered measurement adapter '%s' (%s).", kind, cls.__name__)
    return cls


def unregister_adapter(kind):
    """Remove an adapter from the registry (for tests)."""
    _adapters.pop(kind, None)


def get_adapter(kind):
    """The adapter registered for `kind`."""
    try:
        return _adapters[kind]
    except KeyError:
        raise UnknownMeasurementKindError(kind)


def get_adapters():
    """All registered adapters, by kind."""
    return dict(_adapters)


def infer_kind(channel):
    """The kind of the first registered adapter that claims `channel`."""
    for kind, adapter in _adapters.items():
        if adapter.claims_channel(channel):
            return kind
    raise UnsupportedChannelError(
        f"None of the registered measurement adapters "
        f"({', '.join(_adapters) or 'none are registered'}) can import "
        f"channel '{getattr(channel, 'name', channel)}'."
    )


#
# Adapters
#


class MeasurementAdapter(abc.ABC):
    """Base class of all measurement adapters.

    Adapters hold no per-measurement state: the measurement is always passed in,
    as its `InspectionParameters` and the data object read with them.
    """

    class Meta:
        #: Registry key, stored in `Topography.kind`. Never rename.
        name = None
        #: Human-readable name
        display_name = None

    #: Whether deep zoom images can be rendered
    has_deepzoom = False
    #: Whether there is a canonical ("squeezed") representation of the data
    has_canonical_file = False
    #: Whether `read` returns a ``SurfaceTopography`` object
    yields_surface_topography = False
    #: Whether undefined data points can be filled in
    can_fill_undefined_data = False

    def __str__(self):
        return self.Meta.display_name or self.Meta.name

    @classmethod
    @abc.abstractmethod
    def claims_channel(cls, channel) -> bool:
        """Whether this kind imports `channel`; never raises for one it does not."""

    def channel_fields(self, channel, params) -> dict:
        """The fields of the measurement that `channel` determines, by name.

        Called by the inspection once it has selected the channel. The default
        determines none.
        """
        return {}

    @abc.abstractmethod
    def read(self, reader, params, apply_filters=True, with_instrument_info=True):
        """The in-memory data object of the measurement `params` describe."""

    def render_thumbnail(self, data, width=400, height=400, cmap=None, format="jpeg"):
        """The thumbnail of `data`, as an in-memory image file."""
        raise NotImplementedError(f"'{self}' measurements have no thumbnail.")

    def write_deepzoom(self, data, save) -> None:
        """Render the deep zoom images of `data`, handing each file to
        `save(filename, path)`."""
        raise NotImplementedError(f"'{self}' measurements have no deep zoom images.")

    def write_canonical_file(self, data, path) -> None:
        """Write the canonical representation of `data` to the local `path`."""
        raise NotImplementedError(f"'{self}' measurements have no canonical file.")


class SurfaceTopographyAdapter(MeasurementAdapter):
    """Common base of the height measurements, read through ``SurfaceTopography``."""

    has_canonical_file = True
    yields_surface_topography = True
    can_fill_undefined_data = True

    #: Dimension of the data, checked by `claims_channel`
    dim = None
    #: Whether the kind is uniform, nonuniform or (None) either
    is_uniform = None

    @staticmethod
    def channel_units(channel):
        """The ``(lateral_unit, data_unit)`` of a reader channel.

        A scalar unit means heights, with equal lateral and data units; a tuple
        means data other than heights (adhesion, current, ...).
        """
        if isinstance(channel.unit, tuple):
            return channel.unit
        return channel.unit, channel.unit

    @classmethod
    def claims_channel(cls, channel):
        lateral_unit, data_unit = cls.channel_units(channel)
        if lateral_unit != data_unit:
            # Not heights
            return False
        if channel.dim != cls.dim:
            return False
        return cls.is_uniform is None or bool(channel.is_uniform) == cls.is_uniform

    def channel_fields(self, channel, params):
        fields = {}
        # Resolution: `resolution_y` is None for a line scan
        nb_grid_pts = tuple(int(n) for n in channel.nb_grid_pts)
        fields["resolution_x"] = nb_grid_pts[0]
        fields["resolution_y"] = nb_grid_pts[1] if self.dim == 2 else None

        # Size: the file's wins; without one the user has to enter it
        if channel.physical_sizes is None:
            fields["size_editable"] = True
        else:
            fields["size_editable"] = False
            sizes = tuple(float(s) for s in channel.physical_sizes)
            fields["size_x"] = sizes[0]
            fields["size_y"] = sizes[1] if self.dim == 2 else None

        # Periodicity
        if not channel.is_uniform:
            # Nonuniform line scans do not support periodicity
            fields["is_periodic_editable"] = False
            fields["is_periodic"] = False
        elif params.is_periodic is None:
            fields["is_periodic_editable"] = True
            fields["is_periodic"] = channel.is_periodic
        return fields

    def read(self, reader, params, apply_filters=True, with_instrument_info=True):
        # Imported here: `processing` imports this module
        from .processing import read_topography

        return read_topography(
            reader,
            params,
            apply_filters=apply_filters,
            with_instrument_info=with_instrument_info,
        )

    def write_canonical_file(self, data, path):
        data.to_netcdf(path)


class LineScanAdapter(SurfaceTopographyAdapter):
    """Common base of the one-dimensional height measurements."""

    dim = 1

    def render_thumbnail(self, data, width=400, height=400, cmap=None, format="jpeg"):
        image_file = io.BytesIO()
        dpi = 100
        # Use the object-oriented API rather than `pyplot`. `pyplot` resolves
        # the interactive backend, which on macOS is `macosx`; instantiating
        # its canvas inside a forked Celery worker initializes AppKit on the
        # child side of a fork, which the ObjC runtime aborts with SIGABRT.
        # A bare `Figure` renders through Agg and keeps no global state, so
        # it also removes the need to close the figure (see issue 898).
        fig = Figure(figsize=[width / dpi, height / dpi])
        ax = fig.subplots()
        x, y = data.positions_and_heights()
        ax.plot(x, y, "-")
        ax.set_axis_off()
        fig.savefig(image_file, bbox_inches="tight", dpi=dpi, format=format)
        return image_file


@register_adapter
class TopographyMapAdapter(SurfaceTopographyAdapter):
    """A two-dimensional map of heights."""

    class Meta:
        name = "topography-map"
        display_name = "Topography map"

    dim = 2
    has_deepzoom = True

    def render_thumbnail(self, data, width=400, height=400, cmap=None, format="jpeg"):
        image_file = io.BytesIO()

        # Thumbnail size, keeping the aspect ratio
        sx, sy = data.physical_sizes
        width2 = int(sx * height / sy)
        height2 = int(sy * width / sx)
        if width2 <= width:
            width = width2
        else:
            height = height2

        # Heights rescaled to [0, 1]
        heights = data.heights()
        mx, mn = heights.max(), heights.min()
        span = mx - mn
        if span == 0:
            # A perfectly flat map: normalizing would hand NaNs to the colormap
            heights = np.zeros_like(heights)
        else:
            heights = (heights - mn) / span
        # `matplotlib.colormaps` is the pyplot-free lookup; `None` selects the
        # default, as `pyplot.get_cmap` did.
        if cmap is None:
            cmap = matplotlib.colormaps[matplotlib.rcParams["image.cmap"]]
        elif isinstance(cmap, str):
            cmap = matplotlib.colormaps[cmap]
        colors = (cmap(heights.T) * 255).astype(np.uint8)
        # Without the alpha channel
        PIL.Image.fromarray(colors[:, :, :3]).resize((width, height)).save(
            image_file, format=format
        )
        return image_file

    def write_deepzoom(self, data, save):
        from .processing import write_deepzoom

        write_deepzoom(data, save)


@register_adapter
class UniformLineScanAdapter(LineScanAdapter):
    """A line scan on an evenly spaced grid."""

    class Meta:
        name = "uniform-line-scan"
        display_name = "Uniform line scan"

    is_uniform = True


@register_adapter
class NonuniformLineScanAdapter(LineScanAdapter):
    """A line scan whose sample positions are arbitrary."""

    class Meta:
        name = "nonuniform-line-scan"
        display_name = "Nonuniform line scan"

    is_uniform = False
    # Nonuniform data cannot be interpolated
    can_fill_undefined_data = False


def adapter_of_data(data):
    """The adapter of the built-in kind a ``SurfaceTopography`` object is.

    For data read without a recorded kind, e.g. a measurement inspected before
    kinds were recorded.
    """
    if data.dim == 2:
        return get_adapter(TopographyMapAdapter.Meta.name)
    if data.dim == 1:
        return get_adapter(
            UniformLineScanAdapter.Meta.name
            if data.is_uniform
            else NonuniformLineScanAdapter.Meta.name
        )
    raise UnsupportedChannelError(
        f"Don't know how to handle data of dimension {data.dim}."
    )
