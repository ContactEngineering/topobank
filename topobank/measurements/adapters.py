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

Which metadata a kind has is declared by the two schemas an adapter binds
(:attr:`MeasurementAdapter.Metadata` and :attr:`MeasurementAdapter.FileInfo`), so
a field that does not apply to a kind is absent rather than null. Reading values
out of a file and into those schemas is an adapter's job too: the model owns the
storage plumbing, the adapter owns what the values mean.
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
from django.db.models import BigIntegerField, Value
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast

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


def _resolution_expression(prefix, axis):
    """
    One resolution of a height measurement, as a database expression.

    The resolutions live in the ``file_info`` JSON document, so they arrive as
    text and have to be cast before arithmetic. The cast target is
    ``BigIntegerField`` rather than the 32-bit integer the value actually is,
    and that is not cosmetic: PostgreSQL multiplies ``integer * integer`` as an
    integer, so a map beyond roughly 46000 x 46000 would overflow the product -
    precisely the size of map the memory guard exists to catch.

    A measurement whose document lacks the key (never inspected) yields NULL,
    which propagates through any product and is skipped by aggregates - an
    unsized measurement counts as unknown, not as 0.
    """
    return Cast(
        KeyTextTransform(f"resolution_{axis}", f"{prefix}file_info"),
        BigIntegerField(),
    )


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
    #: Whether undefined data points can be interpolated. Kinds that can have a
    #: ``fill_undefined_data_mode`` in their metadata; the rest have no such field.
    can_fill_undefined_data = False

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
    # Reading metadata out of a file. The inspection task calls these; the model
    # applies what they produce. Anything that knows how a particular reader
    # presents its metadata belongs here, not on the model.
    #

    def read_initial_metadata(self, measurement, channel, metadata) -> None:
        """
        Import optional metadata from `channel` on the first read of a file.

        Called only once per measurement, before the user has had a chance to
        adjust anything -- on later inspections the stored values win, because
        re-importing would overwrite hand-corrected metadata.

        Mutates `metadata` (and, where a value belongs to a column rather than to
        the metadata document, `measurement`) in place. The default imports
        nothing.

        Parameters
        ----------
        measurement : Measurement
            The measurement being inspected.
        channel : object
            The selected channel, as presented by this kind's reader.
        metadata : MeasurementMetadata
            The metadata document being assembled, of this kind's schema.
        """

    def read_file_info(self, measurement, data) -> dict:
        """
        File-derived values to record once `data` has been read.

        Returning a mapping rather than assigning it keeps the storage plumbing --
        which document to write, whether to save -- in one place on the model,
        where it is the same for every kind. The default records nothing.

        Parameters
        ----------
        measurement : Measurement
            The measurement being inspected.
        data : object
            The in-memory data object, as returned by :meth:`read`.

        Returns
        -------
        dict
            Field names of this kind's :attr:`FileInfo` schema, and their values.
        """
        return {}

    def get_undefined_data_status(self, measurement) -> str | None:
        """
        Human-readable description of the undefined-data status, if any.

        None for a kind that has no notion of undefined data points, so that a
        caller can leave the statement out rather than print something untrue.
        """
        return None

    #
    # Job sizing. Peak memory of an analysis is close to linear in the number of
    # datums it holds (see `analysis/sizing.py`), and how many datums a
    # measurement has is a property of its kind. Both hooks abstain by default:
    # a kind that cannot be sized simply is not sized, and the memory guard
    # fails open for it.
    #

    def nb_data_points(self, measurement):
        """
        Number of datums needed to hold `measurement` in memory, or ``None``.

        Read from the inspection cache (`measurement.info`), never from the data
        file: this runs while an analysis is being *submitted*, where opening
        the file would be both slow and outside any error handling. ``None``
        means the size cannot be determined -- the kind has no notion of it, or
        the measurement has not been inspected yet.
        """
        return None

    @classmethod
    def nb_data_points_expression(cls, prefix=""):
        """
        The same quantity as a database expression, or ``None``.

        Aggregating over a dataset's measurements (and learning the
        bytes-per-datum coefficient from past runs) happens in SQL, where
        :meth:`nb_data_points` cannot be called per row. A kind that wants to
        take part in those aggregates therefore supplies an ORM expression over
        the measurement row; ``prefix`` is the join path to it (e.g.
        ``"subject_measurement__"``).

        Whatever this returns must equal :meth:`nb_data_points` on every
        inspected measurement of the kind -- ``test_both_sizing_paths_agree``
        holds the two together. ``None`` (the default) keeps the kind out of
        the SQL aggregates; rows of the kind then count as unknown, not as 0.
        """
        return None

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
    can_fill_undefined_data = True

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
        fill_mode = self.fill_undefined_data_mode_of(measurement)
        if fill_mode != "do-not-fill" and data.is_uniform:
            data = data.interpolate_undefined_data(fill_mode)
        return data.detrend(detrend_mode=meta.detrend_mode)

    @staticmethod
    def physical_sizes_of(measurement):
        """Physical sizes to pass to the reader when the file omits them."""
        raise NotImplementedError

    def fill_undefined_data_mode_of(self, measurement):
        """
        The fill mode in effect, for a kind that may not have the field at all.

        A kind that cannot interpolate undefined data has no
        ``fill_undefined_data_mode`` in its schema, which amounts to never
        filling.
        """
        if not self.can_fill_undefined_data:
            return "do-not-fill"
        return measurement.meta.fill_undefined_data_mode

    #
    # Metadata read out of the file
    #

    def read_initial_metadata(self, measurement, channel, metadata):
        """
        Import acquisition time and instrument description from the channel.

        Both come from ``channel.info``, which is a ``SurfaceTopography`` reader
        convention: a reader that knows nothing about them simply omits the keys,
        which is why every lookup here is allowed to fail.
        """
        # Imported here rather than at module level: this module is imported while
        # apps load, and `SurfaceTopography.Metadata` is only needed on this path.
        from SurfaceTopography.Metadata import InstrumentParametersModel

        try:
            measurement.measurement_date = channel.info["acquisition_time"]
        except:  # noqa: E722
            pass

        try:
            metadata.instrument.name = channel.info["instrument"]["name"]
        except:  # noqa: E722
            pass

        try:
            parameters = channel.info["instrument"]["parameters"]
            metadata.instrument.parameters = InstrumentParametersModel(**parameters)
            # Which kind of instrument this was follows from which parameters it
            # reported: a tip radius comes from a contact-based instrument, a
            # resolution from a microscope-based one.
            if "tip_radius" in parameters:
                metadata.instrument.type = "contact-based"
            elif "resolution" in parameters:
                metadata.instrument.type = "microscope-based"
        except:  # noqa: E722
            metadata.instrument.type = "undefined"

    def read_file_info(self, measurement, data):
        """
        Record what reading the data revealed: undefined data, and the trend removed.

        Both undefined-data values describe the *measured* data, which is why they
        are taken from the bottom of the pipeline rather than from `data` itself:
        with filling enabled the pipeline reports no undefined data by definition,
        which would erase the very information the fill mode was chosen in
        response to.
        """
        from ..manager.utils import detrend_parameters, undefined_data_fraction

        fraction = undefined_data_fraction(data)
        return {
            "undefined_data_fraction": fraction,
            "has_undefined_data": None if fraction is None else fraction > 0,
            # What the detrending actually removed. `data` is the detrended
            # topography, so this reads the fit it performed rather than repeating
            # it.
            "detrend_parameters": detrend_parameters(data),
        }

    def get_undefined_data_status(self, measurement):
        return measurement.info.get_undefined_data_status(
            self.fill_undefined_data_mode_of(measurement)
        )

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

    def nb_data_points(self, measurement):
        """
        Grid points of the map: the product of the two resolutions.

        A map with only one resolution recorded is half-inspected; its size is
        unknown, not `resolution_x` -- pretending otherwise would let a huge map
        past the memory guard on the strength of a partial inspection.
        """
        info = measurement.info
        if info.resolution_x is None or info.resolution_y is None:
            return None
        return info.resolution_x * info.resolution_y

    @classmethod
    def nb_data_points_expression(cls, prefix=""):
        # A missing resolution makes the product NULL (unknown), matching the
        # Python path above. See `_resolution_expression` for why the casts are
        # to `BigIntegerField`.
        return _resolution_expression(prefix, "x") * _resolution_expression(
            prefix, "y"
        )

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

    def nb_data_points(self, measurement):
        """Grid points of the scan: the heights alone, the positions are implied."""
        return measurement.info.resolution_x

    @classmethod
    def nb_data_points_expression(cls, prefix=""):
        return _resolution_expression(prefix, "x")


@register_adapter
class NonuniformLineScanAdapter(LineScanAdapter):
    """A line scan whose sample positions are arbitrary."""

    class Meta:
        name = "nonuniform-line-scan"
        display_name = "Nonuniform line scan"

    Metadata = NonuniformLineScanMetadata
    FileInfo = NonuniformLineScanFileInfo

    is_uniform = False
    #: Non-uniformly spaced points cannot be interpolated, so this kind has no
    #: `fill_undefined_data_mode` at all.
    can_fill_undefined_data = False

    def nb_data_points(self, measurement):
        """
        Twice the number of samples: arbitrary positions have to be stored too.

        A uniform grid keeps only the heights; here every sample carries its own
        position, so holding the scan in memory costs two values per point.
        """
        if measurement.info.resolution_x is None:
            return None
        return 2 * measurement.info.resolution_x

    @classmethod
    def nb_data_points_expression(cls, prefix=""):
        return _resolution_expression(prefix, "x") * Value(
            2, output_field=BigIntegerField()
        )


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
