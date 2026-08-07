"""
Measurement types.

A :class:`MeasurementType` is the strategy that binds a stored
:class:`~topobank.manager.models.Measurement` record to a metadata schema and to
the in-memory *data object* that represents the actual data. It owns everything
that depends on what kind of measurement is being handled: how the data file is
read, which metadata the file provides, and which derived artifacts
(thumbnails, canonical files, ...) can be generated.

The three built-in types cover height data and share
:class:`SurfaceTopographyType`, which contains everything that goes through
``SurfaceTopography.IO``. A measurement type for an entirely different modality
(an XPS spectrum, say) subclasses :class:`MeasurementType` directly and imports
its own data package; nothing in this module needs to know about it.
"""

import abc
import dataclasses
import datetime
import io
import logging
import os.path
import tempfile
from typing import Optional

import matplotlib
import numpy as np
import PIL
from django.conf import settings
from django.core.files import File
from django.core.files.base import ContentFile
from matplotlib.figure import Figure
from SurfaceTopography.Exceptions import UndefinedDataError
from SurfaceTopography.Support.UnitConversion import get_unit_conversion_factor

from .channels import (
    UnsupportedChannelError,
    occurrence_for,
    resolve_channel,
)
from .registry import register_measurement_type
from .schemas import (
    ChannelInfo,
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


class UnsupportedFileError(Exception):
    """No registered measurement type can open this data file."""


@dataclasses.dataclass
class FileInspection:
    """
    Result of opening a measurement's data file.

    Attributes
    ----------
    reader : object
        The open reader, kept so that the caller can read data without opening
        the file a second time.
    format : str
        Identifier of the file format, stored in ``Measurement.datafile_format``.
    channels : list of ChannelInfo
        Inventory of all channels in the file, in file order. The position in
        this list is the reader's channel index.
    default_index : int
        Index of the channel the reader considers the default.
    """

    reader: object
    format: str
    channels: list
    default_index: int = 0

    @property
    def channel_names(self):
        """Names of all channels, in file order."""
        return [channel.name for channel in self.channels]

    def resolve(self, name, occurrence=None):
        """Return the index of the channel identified by `name`/`occurrence`."""
        return resolve_channel(self.channel_names, name, occurrence)

    def occurrence_for(self, index):
        """Occurrence ordinal to record for the channel at `index`."""
        return occurrence_for(self.channel_names, index)


@dataclasses.dataclass
class InspectionResult:
    """
    Metadata and cached values derived from a measurement's data file.

    Attributes
    ----------
    metadata : MeasurementMetadata
        Metadata after merging what the file provides into what was stored.
    file_info : MeasurementFileInfo
        File-derived cache.
    measurement_date : datetime.date, optional
        Acquisition date read from the file. Only suggested on first inspection;
        the caller decides whether to apply it.
    """

    metadata: MeasurementMetadata
    file_info: MeasurementFileInfo
    measurement_date: Optional[datetime.date] = None


class MeasurementType(abc.ABC):
    """
    Base class of all measurement types.

    Registered subclasses are instantiated once; the singleton is what
    :func:`~topobank.measurements.registry.get_measurement_type` returns. There
    is no per-instance state - the measurement to work on is always passed in.
    """

    class Meta:
        #: Stable registry key, stored in ``Measurement.kind``. Never rename.
        name = None
        #: Human-readable name for the UI.
        display_name = None

    #: Schema of the user-facing metadata.
    Metadata = MeasurementMetadata
    #: Schema of the file-derived cache.
    FileInfo = MeasurementFileInfo

    #
    # Capabilities. These tell the generic machinery which derived artifacts
    # exist for this kind, so it does not have to guess from field values.
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

    #
    # Opening files
    #

    @classmethod
    def sniff(cls, measurement) -> Optional[FileInspection]:
        """
        Try to open a measurement's data file.

        Returns a :class:`FileInspection` if this family of measurement types can
        read the file, or ``None`` if it cannot. Types that share a file format
        share this implementation, so the registry opens the file only once.
        """
        return None

    #
    # Reading data
    #

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
            Whether the cached canonical representation may be used instead of
            the original file. (Default: True)
        apply_filters : bool, optional
            Whether the stored corrections (detrending, filling of undefined
            data) are applied. (Default: True)
        return_reader : bool, optional
            If True, return a tuple of data object and reader. (Default: False)
        """
        raise NotImplementedError

    #
    # Inspection
    #

    @abc.abstractmethod
    def inspect(self, measurement, inspection, channel_index) -> InspectionResult:
        """
        Derive metadata and cached values from a measurement's data file.

        Must not mutate `measurement`; the caller applies the result. This lets
        the caller reject a file (for instance because its metadata is
        incomplete) without leaving a half-updated record behind.

        Parameters
        ----------
        measurement : Measurement
            The measurement being inspected.
        inspection : FileInspection
            The opened data file.
        channel_index : int
            Index of the selected channel within ``inspection.channels``.
        """
        raise NotImplementedError

    def read_from_inspection(self, measurement, inspection, apply_filters: bool = True):
        """
        Read the data object during an inspection.

        The default reopens the file; types whose reader is reusable override this
        to read straight from ``inspection.reader``.
        """
        return self.read(measurement, allow_canonical=False, apply_filters=apply_filters)

    #
    # Derived artifacts. The defaults do nothing, so a type only implements what
    # it actually supports.
    #

    def refresh_derived_cache(self, measurement, data, file_info) -> None:
        """Update `file_info` in place with values computed from `data`."""

    def make_thumbnail(self, measurement, data) -> None:
        """Generate the thumbnail and assign it to ``measurement.thumbnail``."""

    def make_deepzoom(self, measurement, data) -> None:
        """Generate Deep Zoom images and assign them to ``measurement.deepzoom``."""

    def make_canonical_file(self, measurement, data) -> None:
        """Generate the canonical representation of the data."""


class SurfaceTopographyType(MeasurementType):
    """
    Common base of the measurement types backed by ``SurfaceTopography``.

    Everything that goes through ``SurfaceTopography.IO`` lives here: opening
    files, mapping channels onto measurement kinds, reading data objects, and the
    canonical NetCDF representation. Concrete subclasses only declare their
    schemas and the few details that genuinely differ between a map and a line
    scan.
    """

    yields_surface_topography = True
    has_canonical_file = True

    #
    # Opening files
    #

    @classmethod
    def sniff(cls, measurement):
        # Imported here rather than at module level: `manager.utils` pulls in
        # Django machinery, and this module is imported while apps load.
        from ..manager.utils import get_topography_reader

        reader = get_topography_reader(measurement.datafile.file)
        channels = [
            cls.describe_channel(channel) for channel in reader.channels
        ]
        return FileInspection(
            reader=reader,
            format=reader.format(),
            channels=channels,
            default_index=reader.default_channel.index,
        )

    @staticmethod
    def channel_units(channel):
        """
        Return the ``(lateral_unit, data_unit)`` of a reader channel.

        A scalar unit means the channel contains heights, in which case the
        lateral and data units are the same. A tuple means the data is something
        other than a height (adhesion, current, stiffness, ...).
        """
        if isinstance(channel.unit, tuple):
            lateral_unit, data_unit = channel.unit
            return lateral_unit, data_unit
        return channel.unit, channel.unit

    @classmethod
    def channel_kind(cls, channel):
        """
        Return the measurement kind a reader channel is imported as.

        ``None`` means no built-in type claims the channel. That is currently the
        case for channels that do not contain height data; they are listed in the
        channel inventory but cannot be selected until a measurement type for
        them is registered.
        """
        lateral_unit, data_unit = cls.channel_units(channel)
        if lateral_unit != data_unit:
            # Not height data.
            return None
        if channel.dim == 2:
            return TopographyMapType.Meta.name
        if channel.dim == 1:
            if channel.is_uniform:
                return UniformLineScanType.Meta.name
            return NonuniformLineScanType.Meta.name
        return None

    @classmethod
    def describe_channel(cls, channel):
        """Build the :class:`ChannelInfo` inventory entry of a reader channel."""
        lateral_unit, data_unit = cls.channel_units(channel)
        return ChannelInfo(
            name=channel.name,
            dim=channel.dim,
            unit=lateral_unit,
            data_unit=data_unit,
            kind=cls.channel_kind(channel),
        )

    #
    # Reading data
    #

    def physical_sizes(self, metadata):
        """Return the physical sizes to pass to the reader, as a tuple."""
        return (metadata.size_x,)

    def _reader_kwargs(self, measurement, reader, channel_index):
        """
        Build the keyword arguments for ``reader.topography()``.

        Metadata is only passed on where the file does not provide it itself;
        otherwise the file wins (which is why the corresponding metadata is not
        editable, see :meth:`inspect`).
        """
        metadata = measurement.meta
        channel = reader.channels[channel_index]

        kwargs = dict(
            channel_index=channel_index,
            periodic=getattr(metadata, "is_periodic", False),
        )

        if channel.physical_sizes is None:
            kwargs["physical_sizes"] = self.physical_sizes(metadata)

        if channel.height_scale_factor is None and metadata.height_scale:
            # Only possible and only needed if the file does not specify it.
            kwargs["height_scale_factor"] = metadata.height_scale

        if channel.unit is None:
            kwargs["unit"] = metadata.unit

        kwargs["info"] = self.instrument_info(measurement)
        return kwargs

    def instrument_info(self, measurement):
        """Instrument information in the form the readers expect."""
        instrument = measurement.meta.instrument
        return {
            "instrument": {
                "name": instrument.name,
                "parameters": instrument.parameters.model_dump(exclude_none=True),
            }
        }

    def apply_filters(self, measurement, data):
        """Apply the stored corrections to a freshly read data object."""
        metadata = measurement.meta
        fill_mode = getattr(metadata, "fill_undefined_data_mode", "do-not-fill")
        if fill_mode != "do-not-fill" and data.is_uniform:
            data = data.interpolate_undefined_data(fill_mode)
        return data.detrend(detrend_mode=metadata.detrend_mode)

    def read_from_reader(
        self, measurement, reader, channel_index=None, apply_filters: bool = True
    ):
        """Read the data object from an already opened reader."""
        if channel_index is None:
            channel_index = measurement.resolve_channel_index(reader=reader)
        data = reader.topography(
            **self._reader_kwargs(measurement, reader, channel_index)
        )
        if apply_filters:
            data = self.apply_filters(measurement, data)
        return data

    def read_from_inspection(self, measurement, inspection, apply_filters: bool = True):
        # The file is already open, so there is no reason to open it again.
        return self.read_from_reader(
            measurement,
            inspection.reader,
            channel_index=inspection.resolve(
                measurement.channel_name, measurement.channel_occurrence
            ),
            apply_filters=apply_filters,
        )

    def read(
        self,
        measurement,
        allow_canonical: bool = True,
        apply_filters: bool = True,
        return_reader: bool = False,
    ):
        from ..manager.utils import get_topography_reader

        reader = None
        data = None

        if allow_canonical and measurement.squeezed_datafile_id and apply_filters:
            measurement.warn_if_expensive_read()
            # The canonical file already has unit, scaling, detrending and
            # physical sizes applied, so none of that is passed again.
            reader = get_topography_reader(
                measurement.squeezed_datafile.file, format=CANONICAL_DATAFILE_FORMAT
            )
            data = reader.topography(info=self.instrument_info(measurement))
            _log.info(
                "Using canonical datafile instead of original datafile for "
                "measurement id %s.",
                measurement.id,
            )

        if data is None:
            # `exists` finishes a pending upload if the file is not there yet.
            if not measurement.datafile.exists():
                raise RuntimeError(
                    f"Measurement {measurement.id} does not appear to have a "
                    "data file."
                )
            measurement.warn_if_expensive_read()
            reader = get_topography_reader(
                measurement.datafile.file, format=measurement.datafile_format
            )
            data = self.read_from_reader(
                measurement, reader, apply_filters=apply_filters
            )

        if return_reader:
            return data, reader
        return data

    #
    # Inspection
    #

    def resolution(self, channel):
        """Return the resolution entries for the file info of this kind."""
        (n,) = channel.nb_grid_pts
        return dict(resolution_x=int(n))

    def sizes_from_channel(self, channel):
        """Return the size entries provided by the file, for this kind."""
        (s,) = channel.physical_sizes
        return dict(size_x=float(s))

    def inspect(self, measurement, inspection, channel_index) -> InspectionResult:
        channel = inspection.reader.channels[channel_index]

        # Start from the stored metadata where it is compatible, so that values
        # the user has adjusted survive a re-inspection.
        metadata = measurement.metadata_for_kind(self.Meta.name)
        file_info = self.FileInfo(
            channels=inspection.channels, **self.resolution(channel)
        )

        #
        # Metadata the file may provide. Where it does, the file wins and the
        # value is not editable; where it does not, the user has to supply it.
        #
        if channel.physical_sizes is None:
            file_info.size_editable = True
        else:
            file_info.size_editable = False
            for name, value in self.sizes_from_channel(channel).items():
                setattr(metadata, name, value)

        if channel.unit is None:
            file_info.unit_editable = True
        else:
            file_info.unit_editable = False
            lateral_unit, data_unit = self.channel_units(channel)
            if lateral_unit != data_unit:
                raise UnsupportedChannelError(
                    channel.name,
                    "It does not contain height data.",
                )
            metadata.unit = lateral_unit

        if channel.height_scale_factor is None:
            file_info.height_scale_editable = True
        else:
            file_info.height_scale_editable = False
            metadata.height_scale = channel.height_scale_factor

        # Only uniform data supports periodicity. For nonuniform line scans the
        # metadata schema has no `is_periodic` field at all, so there is nothing
        # to reset here - the flag is purely informational for the UI.
        file_info.is_periodic_editable = bool(channel.is_uniform)

        #
        # Optional metadata, taken from the file only on first inspection: on
        # later ones it would override what the user has adjusted.
        #
        measurement_date = None
        if measurement.is_first_inspection:
            measurement_date = channel.info.get("acquisition_time") or None
            if not isinstance(measurement_date, (datetime.date, datetime.datetime)):
                measurement_date = None
            instrument = channel.info.get("instrument") or {}
            name = instrument.get("name")
            if name:
                metadata.instrument.name = name
            parameters = instrument.get("parameters")
            if parameters:
                try:
                    metadata.instrument.parameters = parameters
                except Exception:
                    _log.warning(
                        "Ignoring unusable instrument parameters %r in the data "
                        "file of measurement %s.",
                        parameters,
                        measurement.id,
                    )
                else:
                    if "tip_radius" in parameters:
                        metadata.instrument.type = "contact-based"
                    elif "resolution" in parameters:
                        metadata.instrument.type = "microscope-based"

        return InspectionResult(
            metadata=metadata,
            file_info=file_info,
            measurement_date=measurement_date,
        )

    #
    # Derived artifacts
    #

    def refresh_derived_cache(self, measurement, data, file_info) -> None:
        """Cache undefined-data and detrending information plus the bandwidth."""
        from ..manager.utils import detrend_parameters, undefined_data_fraction

        # How much of the original data file is undefined. Taken from the bottom
        # of the pipeline rather than from `data` itself: with filling enabled
        # the pipeline reports no undefined data by definition, which would erase
        # the very information the fill mode was chosen in response to.
        file_info.undefined_data_fraction = undefined_data_fraction(data)
        file_info.has_undefined_data = (
            None
            if file_info.undefined_data_fraction is None
            else file_info.undefined_data_fraction > 0
        )

        # What the detrending actually removed. `data` is the detrended
        # topography, so this reads the fit it performed rather than repeating it.
        file_info.detrend_parameters = detrend_parameters(data)

        if data.unit is None:
            return
        bandwidth_lower, bandwidth_upper = data.bandwidth()
        fac = get_unit_conversion_factor(data.unit, "m")
        file_info.bandwidth_lower = fac * bandwidth_lower
        file_info.bandwidth_upper = fac * bandwidth_upper

        try:
            cutoff = data.short_reliability_cutoff()  # float or None
        except UndefinedDataError:
            # Only computable on data without undefined points.
            cutoff = None
        if cutoff is not None:
            cutoff *= fac
        file_info.short_reliability_cutoff = cutoff

    def render_thumbnail(self, measurement, data, width=400, height=400, cmap=None):
        """
        Render a thumbnail image of the data.

        Returns
        -------
        io.BytesIO
            The encoded image.
        """
        image_file = io.BytesIO()
        dpi = 100
        # Use the object-oriented API rather than `pyplot`. `pyplot` resolves the
        # interactive backend, which on macOS is `macosx`; instantiating its
        # canvas inside a forked Celery worker initializes AppKit on the child
        # side of a fork, which the ObjC runtime aborts with SIGABRT. A bare
        # `Figure` renders through Agg and keeps no global state, so it also
        # removes the need to close the figure (see GH 898).
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

    def make_thumbnail(self, measurement, data) -> None:
        from ..files.models import Manifest

        image_file = self.render_thumbnail(measurement, data)
        if measurement.thumbnail is not None:
            measurement.thumbnail.delete()
        filename = f"thumbnail.{settings.TOPOBANK_THUMBNAIL_FORMAT}"
        measurement.thumbnail = Manifest.objects.create(
            permissions=measurement.permissions, filename=filename, kind="der"
        )
        measurement.thumbnail.save_file(ContentFile(image_file.getvalue()))

    def make_canonical_file(self, measurement, data) -> None:
        """
        Write the canonical ("squeezed") NetCDF representation.

        All corrections are already applied in this file, which makes it much
        faster to load than the original.
        """
        from ..files.models import Manifest

        with tempfile.NamedTemporaryFile() as tmp:
            data.to_netcdf(tmp.name)
            if measurement.squeezed_datafile:
                measurement.squeezed_datafile.delete()
            _, basename = os.path.split(measurement.datafile.filename)
            stem, _ = os.path.splitext(basename)
            measurement.squeezed_datafile = Manifest.objects.create(
                permissions=measurement.permissions,
                filename=f"{stem}-squeezed.nc",
                kind="der",
                file=File(open(tmp.name, mode="rb")),
            )


@register_measurement_type
class TopographyMapType(SurfaceTopographyType):
    """A two-dimensional map of surface heights."""

    class Meta:
        name = "topography-map"
        display_name = "Topography map"

    Metadata = TopographyMapMetadata
    FileInfo = TopographyMapFileInfo

    has_deepzoom = True
    # Two-dimensional data can be large, and loading it in the web server
    # process is a performance problem.
    is_expensive_to_read = True

    def physical_sizes(self, metadata):
        return metadata.size_x, metadata.size_y

    def resolution(self, channel):
        nx, ny = (int(n) for n in channel.nb_grid_pts)
        return dict(resolution_x=nx, resolution_y=ny)

    def sizes_from_channel(self, channel):
        sx, sy = (float(s) for s in channel.physical_sizes)
        return dict(size_x=sx, size_y=sy)

    def render_thumbnail(self, measurement, data, width=400, height=400, cmap=None):
        image_file = io.BytesIO()

        # Keep the aspect ratio of the data.
        sx, sy = data.physical_sizes
        width2 = int(sx * height / sy)
        height2 = int(sy * width / sx)
        if width2 <= width:
            width = width2
        else:
            height = height2

        # Rescale heights to the interval [0, 1] and colorize.
        heights = data.heights()
        mx, mn = heights.max(), heights.min()
        heights = (heights - mn) / (mx - mn)
        # `matplotlib.colormaps` is the pyplot-free lookup; `None` selects the
        # default, as `pyplot.get_cmap` did.
        if cmap is None:
            cmap = matplotlib.colormaps[matplotlib.rcParams["image.cmap"]]
        elif isinstance(cmap, str):
            cmap = matplotlib.colormaps[cmap]
        colors = (cmap(heights.T) * 255).astype(np.uint8)
        # Drop the alpha channel before writing.
        PIL.Image.fromarray(colors[:, :, :3]).resize((width, height)).save(
            image_file, format=settings.TOPOBANK_THUMBNAIL_FORMAT
        )
        return image_file

    def make_deepzoom(self, measurement, data) -> None:
        from ..files.models import ManifestSet
        from ..manager.utils import render_deepzoom

        if measurement.deepzoom is not None:
            measurement.deepzoom.delete()
        measurement.deepzoom = ManifestSet.objects.create(
            permissions=measurement.permissions
        )
        render_deepzoom(data, measurement.deepzoom)


@register_measurement_type
class UniformLineScanType(SurfaceTopographyType):
    """A line scan of surface heights on a uniform grid."""

    class Meta:
        name = "uniform-line-scan"
        display_name = "Uniform line scan"

    Metadata = UniformLineScanMetadata
    FileInfo = UniformLineScanFileInfo


@register_measurement_type
class NonuniformLineScanType(SurfaceTopographyType):
    """A line scan of surface heights with non-uniformly spaced points."""

    class Meta:
        name = "nonuniform-line-scan"
        display_name = "Nonuniform line scan"

    Metadata = NonuniformLineScanMetadata
    FileInfo = NonuniformLineScanFileInfo
