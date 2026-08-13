"""
Measurement adapters.

A :class:`MeasurementAdapter` is the strategy that binds a stored
:class:`~topobank.manager.models.Measurement` to the in-memory *data object*
representing its actual data. It owns everything that depends on what kind of
measurement is being handled: which channels can be imported, how the data file
is read, and which derived artifacts exist.

The three built-in types cover height data and share
:class:`SurfaceTopographyAdapter`, which holds everything that goes through
``SurfaceTopography.IO``. A type for an entirely different modality (an XPS
spectrum, say) subclasses :class:`MeasurementAdapter` directly and imports its own
data package; nothing in this module needs to know about it.

At this stage the metadata a type needs still lives in typed columns on the model,
so the methods here read it off the measurement they are handed. Which fields are
meaningful for which kind is therefore still implicit -- ``size_y`` being null is
what makes a record a line scan. Making that explicit is the next step; this one
only moves the kind-dependent *behaviour* out of the model.
"""

import abc
import io
import logging
import os.path
import tempfile

import matplotlib
import numpy as np
import PIL
from django.conf import settings
from django.core.files import File
from django.core.files.base import ContentFile

from .registry import register_adapter
from .schemas import (
    MeasurementFileInfo,
    MeasurementMetadata,
    NonuniformLineScanFileInfo,
    NonuniformLineScanMetadata,
    TopographyMapFileInfo,
    TopographyMapMetadata,
    UniformLineScanFileInfo,
    UniformLineScanMetadata,
)

_log = logging.getLogger(__name__)

#: Format of the canonical ("squeezed") representation of height data.
CANONICAL_DATAFILE_FORMAT = "nc"


class MeasurementAdapter(abc.ABC):
    """
    Base class of all measurement adapters.

    Registered subclasses are instantiated once; that singleton is what
    :func:`~topobank.measurements.registry.get_adapter` returns. There is
    no per-instance state -- the measurement to work on is always passed in.
    """

    class Meta:
        #: Stable registry key, stored in ``Measurement.kind``. Never rename.
        name = None
        #: Human-readable name for the UI.
        display_name = None

    #: Schema of the user-facing metadata, stored in ``Measurement.metadata``.
    Metadata = MeasurementMetadata
    #: Schema of the file-derived cache, stored in ``Measurement.file_info``.
    FileInfo = MeasurementFileInfo

    #
    # Capabilities. These tell the generic machinery which derived artifacts exist
    # for this kind, so it does not have to infer that from field values.
    #
    #: Whether a Deep Zoom Image pyramid is generated.
    has_deepzoom = False
    #: Whether a canonical (preprocessed) representation of the data is stored.
    has_canonical_file = False
    #: Whether :meth:`read` returns a ``SurfaceTopography`` object, and the
    #: measurement can therefore take part in ``SurfaceContainer`` operations.
    yields_surface_topography = False
    #: Whether reading the data is costly enough that doing it outside a Celery
    #: worker deserves a warning.
    is_expensive_to_read = False

    def __str__(self):
        return self.Meta.display_name or self.Meta.name

    @classmethod
    @abc.abstractmethod
    def claims_channel(cls, channel) -> bool:
        """
        Whether this type can import `channel`.

        Called while inspecting a data file, to decide which kind a measurement
        is. Must not raise for channels it does not recognize -- an unrecognized
        channel is simply not claimed.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def read(
        self,
        measurement,
        allow_canonical: bool = True,
        apply_filters: bool = True,
        return_reader: bool = False,
    ):
        """
        Construct the in-memory data object for `measurement`.

        Parameters
        ----------
        measurement : Measurement
            The measurement to read.
        allow_canonical : bool, optional
            Whether the cached canonical representation may be used instead of the
            original file. (Default: True)
        apply_filters : bool, optional
            Whether the stored corrections (detrending, filling of undefined data)
            are applied. (Default: True)
        return_reader : bool, optional
            If True, return a tuple of data object and reader. (Default: False)
        """
        raise NotImplementedError

    #
    # Derived artifacts. The defaults do nothing, so a type only implements what it
    # actually supports.
    #

    def render_thumbnail(self, measurement, data, width=400, height=400, cmap=None):
        """
        Render a thumbnail and return it as an in-memory file.

        Returning the image rather than assigning it keeps the storage plumbing --
        which manifest to replace, which permissions to use -- in one place on the
        model, where it is the same for every kind.
        """
        raise NotImplementedError(
            f"'{self}' measurements do not support thumbnails."
        )

    def make_deepzoom(self, measurement, data, manifest_set) -> None:
        """Render Deep Zoom images into `manifest_set`."""

    def write_canonical_file(self, measurement, data, path) -> None:
        """Write the canonical representation of `data` to `path`."""
        raise NotImplementedError(
            f"'{self}' measurements do not have a canonical file."
        )


class SurfaceTopographyAdapter(MeasurementAdapter):
    """
    Common base of the measurement adapters backed by ``SurfaceTopography``.

    Everything that goes through ``SurfaceTopography.IO`` lives here: reading data
    objects and the canonical NetCDF representation. Concrete subclasses declare
    only what genuinely differs between a map and a line scan.
    """

    yields_surface_topography = True
    has_canonical_file = True

    #: Dimensionality of the data this type imports, checked by
    #: :meth:`claims_channel`.
    dim = None
    #: Whether the type imports uniform data, non-uniform data, or (None) either.
    is_uniform = None

    @staticmethod
    def channel_units(channel):
        """
        Return the ``(lateral_unit, data_unit)`` of a reader channel.

        A scalar unit means the channel contains heights, so the lateral and data
        units are the same. A tuple means the data is something other than a
        height (adhesion, current, stiffness, ...).
        """
        if isinstance(channel.unit, tuple):
            return channel.unit
        return channel.unit, channel.unit

    @classmethod
    def claims_channel(cls, channel):
        lateral_unit, data_unit = cls.channel_units(channel)
        if lateral_unit != data_unit:
            # Not height data, so none of the built-in types can import it.
            return False
        if channel.dim != cls.dim:
            return False
        return cls.is_uniform is None or bool(channel.is_uniform) == cls.is_uniform

    #
    # Reading data
    #

    def read(
        self,
        measurement,
        allow_canonical: bool = True,
        apply_filters: bool = True,
        return_reader: bool = False,
    ):
        # Imported here rather than at module level: this module is imported while
        # apps load, and `manager` pulls in the model layer.
        from ..manager.utils import get_topography_reader

        reader = None
        data = None

        if (
            allow_canonical
            and apply_filters
            and self.has_canonical_file
            and measurement.squeezed_datafile_id
        ):
            self._warn_if_expensive(measurement)
            # The canonical file already has unit, scaling, detrending and physical
            # sizes applied, so none of them are passed here.
            reader = get_topography_reader(
                measurement.squeezed_datafile.file, format=CANONICAL_DATAFILE_FORMAT
            )
            data = reader.topography(info=measurement.instrument_info)
            _log.info(
                "Using canonical datafile instead of original datafile for "
                f"measurement id {measurement.id}."
            )

        if data is None:
            # `exists` finishes a pending upload, so it has to be called even when
            # the answer is discarded.
            if not measurement.datafile.exists():
                raise RuntimeError(
                    f"Measurement {measurement.id} does not appear to have a data "
                    "file."
                )
            reader = get_topography_reader(
                measurement.datafile.file, format=measurement.datafile_format
            )
            data = self.read_from_reader(
                measurement, reader, apply_filters=apply_filters
            )

        return (data, reader) if return_reader else data

    def read_from_reader(self, measurement, reader, apply_filters: bool = True):
        """
        Read the data object from an already opened reader.

        Metadata stored on the measurement fills in whatever the file itself does
        not provide; the file wins wherever it does, so that a reader gaining the
        ability to report a value takes effect on the next read.
        """
        self._warn_if_expensive(measurement)

        meta = measurement.meta
        reader_kwargs = dict(
            channel_index=measurement.data_source,
            # A kind without periodicity is never periodic.
            periodic=getattr(meta, "is_periodic", False),
        )
        channel = reader.channels[
            reader.default_channel.index
            if measurement.data_source is None
            else measurement.data_source
        ]

        if channel.physical_sizes is None:
            reader_kwargs["physical_sizes"] = self.physical_sizes_of(measurement)
        if channel.height_scale_factor is None and meta.height_scale:
            reader_kwargs["height_scale_factor"] = meta.height_scale
        if channel.unit is None:
            reader_kwargs["unit"] = meta.unit
        reader_kwargs["info"] = measurement.instrument_info

        data = reader.topography(**reader_kwargs)
        if apply_filters:
            data = self.apply_filters(measurement, data)
        return data

    def apply_filters(self, measurement, data):
        """Fill undefined data and detrend, according to the stored metadata."""
        meta = measurement.meta
        # A kind that cannot interpolate undefined data has no such field, which
        # is the same as never filling.
        fill_mode = getattr(meta, "fill_undefined_data_mode", "do-not-fill")
        if fill_mode != "do-not-fill" and data.is_uniform:
            data = data.interpolate_undefined_data(fill_mode)
        return data.detrend(detrend_mode=meta.detrend_mode)

    @staticmethod
    def physical_sizes_of(measurement):
        """Physical sizes to pass to the reader when the file omits them."""
        raise NotImplementedError

    def _warn_if_expensive(self, measurement):
        from ..taskapp.utils import in_celery_worker_process

        if self.is_expensive_to_read and not in_celery_worker_process():
            _log.warning(
                f"You are requesting to load a ({self.dim}D) topography and you are "
                "not within in a Celery worker process. This operation is "
                "potentially slow and may require a lot of memory - do not use "
                "`Measurement.read` within the main Django server!"
            )

    #
    # Canonical file
    #

    def write_canonical_file(self, measurement, data, path):
        data.to_netcdf(path)


class LineScanAdapter(SurfaceTopographyAdapter):
    """Common base of the one-dimensional height measurements."""

    dim = 1

    @staticmethod
    def physical_sizes_of(measurement):
        return (measurement.meta.size_x,)

    def render_thumbnail(self, measurement, data, width=400, height=400, cmap=None):
        from matplotlib.figure import Figure

        image_file = io.BytesIO()
        dpi = 100
        # Use the object-oriented API rather than `pyplot`. `pyplot` resolves the
        # interactive backend, which on macOS is `macosx`; instantiating its canvas
        # inside a forked Celery worker initializes AppKit on the child side of a
        # fork, which the ObjC runtime aborts with SIGABRT. A bare `Figure` renders
        # through Agg and keeps no global state, so it also removes the need to
        # close the figure (see issue 898).
        fig = Figure(figsize=[width / dpi, height / dpi])
        ax = fig.subplots()
        x, y = data.positions_and_heights()
        ax.plot(x, y, "-")
        ax.set_axis_off()
        fig.savefig(
            image_file,
            bbox_inches="tight",
            dpi=dpi,
            format=settings.TOPOBANK_THUMBNAIL_FORMAT,
        )
        return image_file


@register_adapter
class TopographyMapAdapter(SurfaceTopographyAdapter):
    """A two-dimensional map of heights."""

    class Meta:
        name = "topography-map"
        display_name = "Topography map"

    Metadata = TopographyMapMetadata
    FileInfo = TopographyMapFileInfo

    dim = 2
    has_deepzoom = True
    # Reading a map means pulling a full 2D array into memory.
    is_expensive_to_read = True

    @staticmethod
    def physical_sizes_of(measurement):
        meta = measurement.meta
        return meta.size_x, meta.size_y

    def render_thumbnail(self, measurement, data, width=400, height=400, cmap=None):
        image_file = io.BytesIO()

        # Compute thumbnail size, keeping the aspect ratio
        sx, sy = data.physical_sizes
        width2 = int(sx * height / sy)
        height2 = int(sy * width / sx)
        if width2 <= width:
            width = width2
        else:
            height = height2

        # Get heights and rescale to the interval [0, 1]
        heights = data.heights()
        mx, mn = heights.max(), heights.min()
        span = mx - mn
        if span == 0:
            # A perfectly flat map -- a zeroed or synthetic surface. Normalizing
            # would divide by zero and hand NaNs to the colormap, whose output for
            # NaN is not something to rely on. Every pixel is the same height, so
            # the bottom of the colormap is the honest rendering.
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
        # Drop the alpha channel before writing
        PIL.Image.fromarray(colors[:, :, :3]).resize((width, height)).save(
            image_file, format=settings.TOPOBANK_THUMBNAIL_FORMAT
        )
        return image_file

    def make_deepzoom(self, measurement, data, manifest_set):
        from ..manager.utils import render_deepzoom

        render_deepzoom(data, manifest_set)


@register_adapter
class UniformLineScanAdapter(LineScanAdapter):
    """A line scan on an evenly spaced grid."""

    class Meta:
        name = "uniform-line-scan"
        display_name = "Uniform line scan"

    Metadata = UniformLineScanMetadata
    FileInfo = UniformLineScanFileInfo

    is_uniform = True


@register_adapter
class NonuniformLineScanAdapter(LineScanAdapter):
    """A line scan whose sample positions are arbitrary."""

    class Meta:
        name = "nonuniform-line-scan"
        display_name = "Nonuniform line scan"

    Metadata = NonuniformLineScanMetadata
    FileInfo = NonuniformLineScanFileInfo

    is_uniform = False


#
# Helpers shared by the model
#


def write_canonical_manifest(measurement, data):
    """
    Write `data` to a new canonical-file manifest and return it.

    Kept here next to the format it writes; the model decides when to call it and
    what to do with the old manifest.
    """
    from ..files.models import Manifest

    adapter = measurement.adapter
    with tempfile.NamedTemporaryFile(suffix=f".{CANONICAL_DATAFILE_FORMAT}") as tmp:
        adapter.write_canonical_file(measurement, data, tmp.name)
        _, basename = os.path.split(measurement.datafile.filename)
        stem, _ = os.path.splitext(basename)
        return Manifest.objects.create(
            permissions=measurement.permissions,
            filename=f"{stem}-squeezed.{CANONICAL_DATAFILE_FORMAT}",
            kind="der",
            file=File(open(tmp.name, mode="rb")),
        )


def write_thumbnail_manifest(measurement, image_file):
    """Write a rendered thumbnail to a new manifest and return it."""
    from ..files.models import Manifest

    manifest = Manifest.objects.create(
        permissions=measurement.permissions,
        filename=f"thumbnail.{settings.TOPOBANK_THUMBNAIL_FORMAT}",
        kind="der",
    )
    manifest.save_file(ContentFile(image_file.getvalue()))
    return manifest
