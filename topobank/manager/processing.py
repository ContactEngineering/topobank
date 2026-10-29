"""Inspecting a measurement's data file, as a function of the file alone.

`inspect_datafile` is the compute half of processing a measurement: it reads the
raw file with the measurement's parameters, writes the derived files (squeezed
NetCDF file, thumbnail, deep zoom images) through a writer, and returns what it
found as an `InspectionResult`. It touches no database and no Django model, so it
can run wherever the file and the writer are reachable: in the Celery worker, as
`Topography.refresh_cache` does, or in a separate process that hands its result
back. `Topography.apply_inspection` is the other half, which records a result.

Only the standard library, NumPy, Pillow, Matplotlib and SurfaceTopography are
imported here, so that a worker without Django can import this module.
"""

import contextlib
import dataclasses
import datetime
import io
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional, Protocol

import matplotlib
import numpy as np
import PIL
from matplotlib.figure import Figure
from SurfaceTopography import open_topography
from SurfaceTopography.Exceptions import UndefinedDataError
from SurfaceTopography.IO import ReaderBase
from SurfaceTopography.IO.DZI import write_dzi
from SurfaceTopography.Metadata import InstrumentParametersModel
from SurfaceTopography.Support.UnitConversion import get_unit_conversion_factor

from ..exceptions import IncompleteMetadataError

_log = logging.getLogger(__name__)

#: Version of the `InspectionResult` format. A result is applied only by code that
#: writes the same version, since the two halves may run in different images.
RESULT_VERSION = 1

#: Detrend modes, ordered by how much they remove (`Topography.DETREND_MODE_CHOICES`)
DETREND_MODES = ("center", "height", "curvature")

#: Instrument types (`Topography.INSTRUMENT_TYPE_*`)
INSTRUMENT_TYPE_UNDEFINED = "undefined"
INSTRUMENT_TYPE_MICROSCOPE_BASED = "microscope-based"
INSTRUMENT_TYPE_CONTACT_BASED = "contact-based"

FILL_UNDEFINED_DATA_MODE_NOFILLING = "do-not-fill"

SQUEEZED_DATAFILE_FORMAT = "nc"

#: Curvature below which a fitted paraboloid is treated as flat. The least-squares
#: fit of a plane leaves quadratic coefficients at the level of numerical noise
#: (~1e-18 / length²), and inverting those yields radii of order 1e17 length
#: units. Scaled by the scan size, genuine curvatures sit many orders of magnitude
#: above this.
_FLAT_CURVATURE = 1e-9

#: Names of the derived files in `InspectionResult.derived`
DERIVED_NAMES = ("thumbnail", "deepzoom", "squeezed_datafile")

#: The fields of a measurement an inspection may determine
INSPECTED_FIELDS = (
    "datafile_format",
    "channel_names",
    "data_source",
    "resolution_x",
    "resolution_y",
    "size_editable",
    "size_x",
    "size_y",
    "unit_editable",
    "unit",
    "height_scale_editable",
    "height_scale",
    "is_periodic_editable",
    "is_periodic",
    "measurement_date",
    "instrument_name",
    "instrument_parameters",
    "instrument_type",
    "undefined_data_fraction",
    "has_undefined_data",
    "detrend_parameters",
    "bandwidth_lower",
    "bandwidth_upper",
    "short_reliability_cutoff",
)


#
# Parameters and result
#


@dataclasses.dataclass(frozen=True)
class InspectionParameters:
    """What an inspection needs to know about a measurement besides its file.

    The measurement's own values (as the database holds them when processing is
    dispatched) and the deployment's settings that shape the derived files.
    `Topography.inspection_parameters` builds them.
    """

    # The measurement
    name: str
    filename: str
    data_source: Optional[int]
    size_x: Optional[float]
    size_y: Optional[float]
    unit: Optional[str]
    height_scale: Optional[float]
    is_periodic: Optional[bool]
    fill_undefined_data_mode: str
    detrend_mode: str
    instrument_name: str
    instrument_parameters: Dict[str, Any]

    # The deployment
    thumbnail_format: str = "jpeg"
    visualization_detrend_mode: Optional[str] = None
    reject_incomplete_metadata: bool = False

    @property
    def is_metadata_complete(self):
        """Whether there is everything needed to actually read the file."""
        return (
            self.size_x is not None
            and self.unit is not None
            and self.height_scale is not None
        )

    def to_dict(self):
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


@dataclasses.dataclass
class InspectionResult:
    """What an inspection found, and the derived files it wrote.

    `fields` holds the measurement's fields the inspection determined, by name;
    a field it did not determine is absent, and the measurement keeps its value.
    `derived` holds, for each derived file the inspection generated, the written
    file (`{"filename", "key", "size"}`, a list of them for the deep zoom images),
    or None where generating it failed and the measurement is left without one;
    a derived file it did not generate is absent and stays as it is.
    """

    fields: Dict[str, Any] = dataclasses.field(default_factory=dict)
    derived: Dict[str, Any] = dataclasses.field(default_factory=dict)
    version: int = RESULT_VERSION

    def to_dict(self):
        """The result in a form that survives JSON."""
        fields = dict(self.fields)
        date = fields.get("measurement_date")
        if isinstance(date, (datetime.date, datetime.datetime)):
            fields["measurement_date"] = date.isoformat()
        if "channel_names" in fields:
            fields["channel_names"] = [list(c) for c in fields["channel_names"]]
        return {"version": self.version, "fields": fields, "derived": self.derived}

    @classmethod
    def from_dict(cls, data):
        return cls(
            fields=dict(data.get("fields", {})),
            derived=dict(data.get("derived", {})),
            version=data.get("version"),
        )

    def written_keys(self):
        """Storage keys of every derived file this result references."""
        keys = []
        for written in self.derived.values():
            for item in written if isinstance(written, list) else [written]:
                if item is not None:
                    keys.append(item["key"])
        return keys


class Writer(Protocol):
    """Where an inspection writes its derived files."""

    def save(self, name: str, path: str) -> Dict[str, Any]:
        """Store the local file `path` as `name`; returns `{"key", "size"}`."""

    def delete(self, keys=None) -> None:
        """Delete `keys` this writer stored, or everything it stored."""


class StorageWriter:
    """Writes derived files under a prefix of a Django storage backend."""

    def __init__(self, storage, prefix):
        self.storage = storage
        self.prefix = prefix.rstrip("/")
        self.keys = []

    def save(self, name, path):
        # Cleaned as a file field cleans the names of uploads
        key = self.storage.generate_filename(f"{self.prefix}/{name}")
        with open(path, "rb") as fobj:
            key = self.storage.save(key, fobj)
        self.keys.append(key)
        return {"key": key, "size": os.path.getsize(path)}

    def delete(self, keys=None):
        """Delete `keys` (by default all) that were stored; failures are logged,
        never raised."""
        keys = list(self.keys if keys is None else keys)
        delete_keys(self.storage, keys)
        deleted = set(keys)
        self.keys = [key for key in self.keys if key not in deleted]


class _RecordingWriter:
    """Passes writes on to `writer` and remembers their keys."""

    def __init__(self, writer):
        self.writer = writer
        self.keys = []

    def save(self, name, path):
        written = self.writer.save(name, path)
        self.keys.append(written["key"])
        return written


def delete_keys(storage, keys):
    """Delete storage `keys`, logging rather than raising a failure."""
    for key in keys:
        try:
            storage.delete(key)
        except Exception as exc:  # deleting is cleanup; never fail on it
            _log.warning("Could not delete derived file %s: %s", key, exc)


#
# Reading
#


def instrument_info(name, parameters):
    """The instrument information to read a measurement with.

    It overrides what the reader finds in the file.
    """
    return {
        "instrument": {
            "name": name,
            "parameters": InstrumentParametersModel(**parameters).model_dump(
                exclude_none=True
            ),
        }
    }


def get_topography_reader(filefield, format: Optional[str] = None) -> ReaderBase:
    """Returns SurfaceTopography.IO.ReaderBase object.

    Parameters
    ----------

    filefield: models.FileField instance or file-like object
        reference to file which should be opened by the reader
    format: str, optional
        specify in which format the file should be interpreted;
        if not given, the format is determined automatically

    Returns
    -------
        Instance of a `ReaderBase` subclass according to the format.
    """
    if not hasattr(filefield, "mode"):
        # Workaround such that the SurfaceTopography module recognizes this as a binary
        # stream
        filefield.mode = "rb"
    if hasattr(filefield, "file") and hasattr(filefield.file, "seek"):
        # make sure the file is rewound
        filefield.file.seek(0)
    reader = open_topography(filefield, format=format)
    return reader


def read_topography(
    reader: ReaderBase,
    params: InspectionParameters,
    apply_filters=True,
    with_instrument_info=True,
):
    """Read the measurement `params` describe from `reader`.

    The file's own metadata takes precedence; the measurement's values fill in
    what the file lacks.

    apply_filters: bool, optional
        If True (default), the instance is detrended and corrected for
        missing artifacts according to the saved parameters.
        (Default: True)
    with_instrument_info: bool, optional
        If True (default), the measurement's instrument information replaces the
        file's. False reads with the file's, for a measurement whose instrument
        fields still hold their defaults (see `Topography.has_instrument_info`).
    """
    reader_kwargs = dict(channel_index=params.data_source, periodic=params.is_periodic)

    channel = reader.channels[
        reader.default_channel.index
        if params.data_source is None
        else params.data_source
    ]

    # Set size if physical size was not given in datafile
    # (see also  TopographyCreateWizard.get_form_initial)
    # Physical size is always a tuple or None.
    if channel.physical_sizes is None:
        if params.size_y is None:
            reader_kwargs["physical_sizes"] = (params.size_x,)
        else:
            reader_kwargs["physical_sizes"] = params.size_x, params.size_y

    if channel.height_scale_factor is None and params.height_scale:
        # Adjust height scale to value chosen by user
        reader_kwargs["height_scale_factor"] = params.height_scale

        # This is only possible and needed, if no height scale was given in the data file already.
        # So default is to use the factor from the file.

    # Set the unit, if not already given by file contents
    if channel.unit is None:
        reader_kwargs["unit"] = params.unit

    # Populate instrument information
    if with_instrument_info:
        reader_kwargs["info"] = instrument_info(
            params.instrument_name, params.instrument_parameters
        )

    # Eventually get topography from module "SurfaceTopography" using the given keywords
    topo = reader.topography(**reader_kwargs)
    if apply_filters:
        if (
            params.fill_undefined_data_mode != FILL_UNDEFINED_DATA_MODE_NOFILLING
            and topo.is_uniform
        ):
            topo = topo.interpolate_undefined_data(params.fill_undefined_data_mode)
        topo = topo.detrend(detrend_mode=params.detrend_mode)
    return topo


#
# What a read topography tells
#


def detrend_parameters(st_topo):
    """
    The trend that was subtracted from a measurement, in physical units.

    A detrended topography carries the coefficients of the polynomial it removed,
    but in units of fractional position (`x = index / nb_grid_pts`), which are not
    meaningful to report. They are converted here: slopes to the dimensionless
    ratio of height over lateral distance, curvatures to a radius in the lateral
    unit of the measurement.

    The mixed term of a fitted paraboloid is left out. It is part of the removed
    trend, but it does not describe a radius in either lateral direction, which is
    what a reader is after.

    Parameters
    ----------
    st_topo : SurfaceTopography.HeightContainer.AbstractHeightContainer
        Topography, as returned by `detrend`.

    Returns
    -------
    dict
        Keys `slope_x`, `slope_y`, `radius_x` and `radius_y`, each present only
        where the fit determines it: a detrend mode that only subtracts the mean
        yields an empty dict, a line scan has no `y` component, and a direction the
        fit found to be flat has no radius. Radii are in the lateral unit of the
        measurement.
    """
    coeffs = getattr(st_topo, "coeffs", None)
    if coeffs is None:
        # Not a detrended topography; nothing was fitted.
        return {}

    directions = ["x", "y"][: st_topo.dim]
    sizes = st_topo.physical_sizes
    parameters = {}

    # A fit on a uniform grid is parameterized in fractional position
    # (`x = index / nb_grid_pts`), so its linear coefficients have to be divided
    # by the extent of the scan; a fit on a nonuniform line scan uses the real
    # positions and is already per unit length.
    extents = sizes if st_topo.is_uniform else (1,) * len(directions)

    # coeffs[0] is the offset, followed by one linear coefficient per direction.
    # A mode that only subtracts the mean stops after the offset.
    for index, (direction, extent) in enumerate(zip(directions, extents), start=1):
        if len(coeffs) > index:
            parameters[f"slope_{direction}"] = float(coeffs[index]) / extent

    # `curvatures` returns 1/R per direction, followed by the mixed term, and
    # already accounts for the parameterization of the fit.
    curvatures = getattr(st_topo, "curvatures", ())
    for direction, size, curvature in zip(directions, sizes, curvatures):
        if abs(curvature) * size > _FLAT_CURVATURE:
            parameters[f"radius_{direction}"] = 1 / float(curvature)

    return parameters


def undefined_data_fraction(st_topo):
    """
    Fraction of the data points of a measurement that carry no value, in [0, 1].

    The number describes the data as it was *measured*, not the filtered
    instance: a topography with filling enabled reports no undefined data by
    definition (`interpolate_undefined_data_harmonic` overrides
    `has_undefined_data` to False and replaces the mask with interpolated
    values), so asking the instance itself would report zero for exactly those
    measurements where the answer matters. The mask is therefore read from the
    bottom of the pipeline, which is the node holding the data as read from the
    file.

    Parameters
    ----------
    st_topo : SurfaceTopography.HeightContainer.AbstractHeightContainer
        Topography, possibly the result of a chain of filters.

    Returns
    -------
    float or None
        The fraction of undefined data points, or None for an empty topography.
    """
    while hasattr(st_topo, "parent_topography"):
        st_topo = st_topo.parent_topography
    # Topographies without any undefined data carry a plain array rather than a
    # masked one; `getmaskarray` returns an all-False mask for those.
    mask = np.ma.getmaskarray(st_topo.heights())
    if mask.size == 0:
        return None
    return float(mask.sum()) / mask.size


def bandwidth_fields(st_topo):
    """The bandwidth and reliability cutoff of `st_topo`, in meters, by field name.

    Empty for a topography without a unit, whose fields are then left as they are.
    """
    if st_topo.unit is None:
        return {}
    bandwidth_lower, bandwidth_upper = st_topo.bandwidth()
    fac = get_unit_conversion_factor(st_topo.unit, "m")
    try:
        short_reliability_cutoff = st_topo.short_reliability_cutoff()  # float or None
    except UndefinedDataError:
        # Short reliability cutoff can only be computed on topographies without undefined data
        short_reliability_cutoff = None
    if short_reliability_cutoff is not None:
        short_reliability_cutoff *= fac
    return {
        "bandwidth_lower": fac * bandwidth_lower,
        "bandwidth_upper": fac * bandwidth_upper,
        "short_reliability_cutoff": short_reliability_cutoff,  # None is also saved
    }


#
# Derived files
#


def visualization_topography(st_topo, detrend_mode, visualization_detrend_mode):
    """
    Return the topography as its thumbnail and deep zoom images show it.

    The images are a visualization, not data. A tilt of the sample across the
    scan easily dwarfs its roughness and then renders as a plain color
    gradient, so a deployment can remove tilt (or curvature) from the images
    through ``TOPOBANK_VISUALIZATION_DETREND_MODE`` even when the
    measurement's own ``detrend_mode`` keeps it. A measurement that is
    already detrended at least that far is shown as it is. Analyses and the
    squeezed datafile are unaffected.

    Parameters
    ----------
    st_topo : SurfaceTopography.Topography or line scan
        The measurement as read with its own filters applied.
    detrend_mode : str
        The measurement's own detrend mode.
    visualization_detrend_mode : str or None
        The detrending the images get at least.

    Returns
    -------
    st_topo : SurfaceTopography.Topography or line scan
        The topography to render.
    """
    mode = visualization_detrend_mode
    if mode is None:
        return st_topo
    if mode not in DETREND_MODES:
        raise ValueError(
            f"TOPOBANK_VISUALIZATION_DETREND_MODE must be one of {list(DETREND_MODES)} "
            f"or None, not '{mode}'."
        )
    if DETREND_MODES.index(mode) <= DETREND_MODES.index(detrend_mode):
        return st_topo
    return st_topo.detrend(detrend_mode=mode)


def render_thumbnail(st_topo, width=400, height=400, cmap=None, format="jpeg"):
    """
    Make thumbnail image.

    Parameters
    ----------
    st_topo : SurfaceTopography.Topography or line scan
        The topography to render.
    width : int, optional
        Maximum width of the thumbnail. (Default: 400)
    height : int, optional
        Maximum height of the thumbnail. (Default: 400)
    cmap : str or colormap, optional
        Color map for rendering the topography. (Default: None)
    format : str, optional
        Image format, as Pillow and Matplotlib name it. (Default: "jpeg")

    Returns
    -------
    image : bytes-like
        Thumbnail image.
    """
    image_file = io.BytesIO()
    if st_topo.dim == 1:
        dpi = 100
        # Use the object-oriented API rather than `pyplot`. `pyplot` resolves
        # the interactive backend, which on macOS is `macosx`; instantiating
        # its canvas inside a forked Celery worker initializes AppKit on the
        # child side of a fork, which the ObjC runtime aborts with SIGABRT.
        # A bare `Figure` renders through Agg and keeps no global state, so
        # it also removes the need to close the figure (see issue 898).
        fig = Figure(figsize=[width / dpi, height / dpi])
        ax = fig.subplots()
        x, y = st_topo.positions_and_heights()
        ax.plot(x, y, "-")
        ax.set_axis_off()
        fig.savefig(image_file, bbox_inches="tight", dpi=100, format=format)
    elif st_topo.dim == 2:
        # Compute thumbnail size (keeping aspect ratio)
        sx, sy = st_topo.physical_sizes
        width2 = int(sx * height / sy)
        height2 = int(sy * width / sx)
        if width2 <= width:
            width = width2
        else:
            height = height2

        # Get heights and rescale to interval 0, 1
        heights = st_topo.heights()
        mx, mn = heights.max(), heights.min()
        heights = (heights - mn) / (mx - mn)
        # Get color map. `matplotlib.colormaps` is the pyplot-free lookup;
        # `None` selects the default, as `pyplot.get_cmap` did.
        if cmap is None:
            cmap = matplotlib.colormaps[matplotlib.rcParams["image.cmap"]]
        elif isinstance(cmap, str):
            cmap = matplotlib.colormaps[cmap]
        # Convert to image
        colors = (cmap(heights.T) * 255).astype(np.uint8)
        # Remove alpha channel before writing
        PIL.Image.fromarray(colors[:, :, :3]).resize((width, height)).save(
            image_file, format=format
        )
    else:
        raise RuntimeError(
            f"Don't know how to create thumbnail for topography of dimension {st_topo.dim}."
        )
    return image_file


def write_deepzoom(
    data,
    save,
    physical_sizes=None,
    unit=None,
    quality=95,
    colorbar_title=None,
    cmap=None,
    storage_prefix="",
    generate_netcdf=True,
):
    """
    Make JPG Deep Zoom Image (DZI) files given data on a two-dimensional grid,
    and hand each to `save(filename, path)`.

    See `topobank.manager.utils.render_deepzoom` for the parameters; this is its
    body, without the assumption about where the files go.
    """
    with tempfile.TemporaryDirectory() as tmpdirname:
        try:
            # This is a Topography
            filenames = data.to_dzi(
                "dzi",
                root_directory=tmpdirname,
                meta_format="json",
                quality=quality,
                cmap=cmap,
            )
        except AttributeError:
            # This is likely just a numpy array
            if physical_sizes is None or unit is None:
                raise ValueError(
                    "You need to provide `physical_sizes` and `unit` when visualizing "
                    "numpy arrays."
                )
            filenames = write_dzi(
                data,
                "dzi",
                physical_sizes,
                unit,
                root_directory=tmpdirname,
                meta_format="json",
                quality=quality,
                colorbar_title=colorbar_title,
                cmap=cmap,
            )
        for filename in filenames:
            # Strip tmp directory
            save(
                os.path.join(storage_prefix, filename[len(tmpdirname) + 1:]),
                filename,
            )

        # Generate NetCDF tiles for interactive viewer
        if generate_netcdf:
            try:
                # This is a Topography
                nc_filenames = data.to_dzi(
                    "dzi-nc",
                    root_directory=tmpdirname,
                    meta_format="json",
                    format="nc",
                )
            except AttributeError:
                # This is likely just a numpy array
                if physical_sizes is not None and unit is not None:
                    nc_filenames = write_dzi(
                        data,
                        "dzi-nc",
                        physical_sizes,
                        unit,
                        root_directory=tmpdirname,
                        meta_format="json",
                        format="nc",
                    )
                else:
                    nc_filenames = []
            for filename in nc_filenames:
                # Strip tmp directory
                save(
                    os.path.join(storage_prefix, filename[len(tmpdirname) + 1:]),
                    filename,
                )


def _write_thumbnail(st_topo, params, writer):
    image = render_thumbnail(
        st_topo=visualization_topography(
            st_topo, params.detrend_mode, params.visualization_detrend_mode
        ),
        format=params.thumbnail_format,
    )
    filename = f"thumbnail.{params.thumbnail_format}"
    with tempfile.NamedTemporaryFile() as tmp:
        tmp.write(image.getvalue())
        tmp.flush()
        return {"filename": filename, **writer.save(f"thumbnail/{filename}", tmp.name)}


def _write_deepzoom(st_topo, params, writer):
    written = []

    def save(filename, path):
        written.append({"filename": filename, **writer.save(f"deepzoom/{filename}", path)})

    write_deepzoom(
        visualization_topography(
            st_topo, params.detrend_mode, params.visualization_detrend_mode
        ),
        save,
    )
    return written


#: The longest name of a derived file (as `Manifest.filename` holds it)
MAX_FILENAME_LENGTH = 255


def _write_squeezed(st_topo, params, writer):
    orig_stem, _ = os.path.splitext(os.path.basename(params.filename))
    suffix = "-squeezed.nc"
    filename = f"{orig_stem[:MAX_FILENAME_LENGTH - len(suffix)]}{suffix}"
    with tempfile.NamedTemporaryFile() as tmp:
        st_topo.to_netcdf(tmp.name)
        return {"filename": filename, **writer.save(f"squeezed/{filename}", tmp.name)}


_DERIVED_WRITERS = {
    "thumbnail": ("thumbnail", _write_thumbnail),
    "deepzoom": ("deep zoom images", _write_deepzoom),
    "squeezed_datafile": ("squeezed datafile", _write_squeezed),
}

# The timer step under which each derived file is written
_DERIVED_TIMERS = {
    "thumbnail": "make_thumbnail",
    "deepzoom": "make_deepzoom",
    "squeezed_datafile": "make_squeezed",
}


def write_derived(name, st_topo, params, writer):
    """Write the derived file `name` of `st_topo` (one of `DERIVED_NAMES`).

    Returns the written file (`{"filename", "key", "size"}`, a list of them for
    the deep zoom images). A failure deletes whatever part of it was written
    before it is raised.
    """
    _, write = _DERIVED_WRITERS[name]
    recording = _RecordingWriter(writer)
    try:
        return write(st_topo, params, recording)
    except BaseException:
        writer.delete(recording.keys)
        raise


def _soft_time_limit_exceeded():
    """Celery's soft time limit exception, where Celery is installed."""
    try:
        from celery.exceptions import SoftTimeLimitExceeded
    except ImportError:  # pragma: no cover - Celery ships with topobank
        return ()
    return (SoftTimeLimitExceeded,)


def _get_unit(channel):
    if isinstance(channel.unit, tuple):
        lateral_unit, data_unit = channel.unit
        return data_unit
    return channel.unit


#
# The inspection
#


def inspect_datafile(
    source,
    params: InspectionParameters,
    writer: Writer,
    timer=None,
    label=None,
    result: Optional[InspectionResult] = None,
) -> InspectionResult:
    """
    Inspect the data file `source` of the measurement `params` describe.

    Reads the file's channels and metadata, and, if the metadata is complete,
    reads the topography and writes its squeezed datafile, thumbnail and deep
    zoom images through `writer`. The file's metadata takes precedence over the
    measurement's, except for what the user can only enter (and the instrument
    data, which is taken from the file only on the first inspection).

    A derived file that cannot be generated is logged and recorded as None; any
    other error is raised. What was found up to then is in `result`, where the
    caller passed one in, and the files written so far are still in storage:
    the caller deletes them through the writer.

    Parameters
    ----------
    source : file-like
        The raw data file.
    params : InspectionParameters
        The measurement's values and the deployment's settings.
    writer : Writer
        Where the derived files go.
    timer : callable, optional
        Context manager factory timing the named steps.
    label : str, optional
        How to name the measurement in log messages.
    result : InspectionResult, optional
        The result to fill in, which the caller keeps if inspecting fails.
        By default a new one, which is returned.
    """
    if timer is None:

        def timer(name):
            return contextlib.nullcontext()

    label = label or repr(params.name)
    if result is None:
        result = InspectionResult()
    _inspect(source, params, writer, timer, label, result)
    return result


def _inspect(source, params, writer, timer, label, result):
    fields = result.fields

    def set_field(name, value):
        fields[name] = value

    # Check if this is the first time we are opening this file...
    populate_initial_metadata = params.data_source is None

    _log.info(f"Caching properties of topography {label}...")

    # Open topography file
    with timer("get_topography_reader"):
        reader = get_topography_reader(source)
        set_field("datafile_format", reader.format())

    # Update channel names
    channel_names = [(channel.name, _get_unit(channel)) for channel in reader.channels]
    set_field("channel_names", channel_names)

    # Idiot check
    if len(channel_names) == 0:
        raise RuntimeError(
            f"Datafile of measurement '{params.name}' could be opened, but it "
            "appears to contain no valid data."
        )

    # Check whether the user already selected a (valid) channel, if not set to
    # default channel. This is kept in a local variable until the file's
    # metadata has been checked (below), so that a rejected inspection leaves
    # the measurement's channel as it was.
    data_source = params.data_source
    if data_source is None or data_source < 0 or data_source >= len(channel_names):
        data_source = reader.default_channel.index

    # Select channel
    channel = reader.channels[data_source]

    # Reject files with incomplete metadata if this instance is configured to do
    # so. The file is of a supported format and could be read, but the metadata
    # required to process it (physical size, unit) is missing and would normally
    # have to be entered manually through the UI. A field is considered missing
    # only if neither the file nor the existing database entry provides it, so
    # container/zip imports (which populate this metadata from `index.json` before
    # inspection) are not affected.
    if params.reject_incomplete_metadata:
        size_missing = channel.physical_sizes is None and params.size_x is None
        unit_missing = channel.unit is None and params.unit is None
        if size_missing or unit_missing:
            missing = []
            if size_missing:
                missing.append("physical size")
            if unit_missing:
                missing.append("unit")
            raise IncompleteMetadataError(
                f"The file format '{fields['datafile_format']}' is supported, but the "
                f"file does not contain complete metadata. The following required "
                f"metadata could not be read from the file: {', '.join(missing)}. "
                f"This instance is configured to reject files with incomplete "
                f"metadata."
            )

    set_field("data_source", data_source)

    #
    # Look for necessary metadata. The file's values override the measurement's.
    # This may be necessary if the underlying reader changes (e.g. through bug
    # fixes).
    #

    # Resolution
    if channel.dim == 1:
        (n,) = channel.nb_grid_pts
        set_field("resolution_x", int(n))
        set_field("resolution_y", None)  # This indicates that this is a line scan
    elif channel.dim == 2:
        resolution_x, resolution_y = (int(n) for n in channel.nb_grid_pts)
        set_field("resolution_x", resolution_x)
        set_field("resolution_y", resolution_y)
    else:
        # This should not happen
        raise NotImplementedError(
            f"Cannot handle topographies of dimension {channel.dim}."
        )

    # Size
    if channel.physical_sizes is None:
        # Data file *does not* provide size information; the user must provide it
        set_field("size_editable", True)
    else:
        # Data file *does* provide size information; the user cannot override it
        set_field("size_editable", False)
        # Reset size information here
        if channel.dim == 1:
            (s,) = channel.physical_sizes
            set_field("size_x", float(s))
            set_field("size_y", None)
        elif channel.dim == 2:
            size_x, size_y = (float(s) for s in channel.physical_sizes)
            set_field("size_x", size_x)
            set_field("size_y", size_y)
        else:
            # This should not happen
            raise NotImplementedError(
                f"Cannot handle topographies of dimension {channel.dim}."
            )

    # Unit
    if channel.unit is None:
        # Data file *does not* provide unit information; the user must provide it
        set_field("unit_editable", True)
    else:
        # Data file *does* provide unit information; the user cannot override it
        set_field("unit_editable", False)
        # Reset unit information here
        if isinstance(channel.unit, tuple):
            raise NotImplementedError(
                f"Data channel '{channel.name}' contains information that is not "
                "height."
            )
        set_field("unit", channel.unit)

    # Height scale
    if channel.height_scale_factor is None:
        # Data file *does not* provide height scale information; the user must provide it
        set_field("height_scale_editable", True)
    else:
        # Data file *does* provide height scale information; the user cannot override it
        set_field("height_scale_editable", False)
        # Reset unit information here
        set_field("height_scale", channel.height_scale_factor)

    # Populate information on periodicity
    if not channel.is_uniform:
        # This is a nonuniform line scan that does not support periodicity
        set_field("is_periodic_editable", False)
        set_field("is_periodic", False)
    elif params.is_periodic is None:
        # This is a uniform line scan or map, periodicity is supported
        set_field("is_periodic_editable", True)
        set_field("is_periodic", channel.is_periodic)

    #
    # We now look for optional metadata. Only import it from the file on first read,
    # otherwise we may override what the user has painfully adjusted when refreshing
    # the cache.
    #

    if populate_initial_metadata:
        # Measurement time
        try:
            set_field("measurement_date", channel.info["acquisition_time"])
        except:  # noqa: E722
            pass

        # Instrument name
        try:
            set_field("instrument_name", channel.info["instrument"]["name"])
        except:  # noqa: E722
            pass

        # Instrument parameters
        try:
            instrument_parameters = channel.info["instrument"]["parameters"]
            set_field("instrument_parameters", instrument_parameters)
            if "tip_radius" in instrument_parameters:
                set_field("instrument_type", INSTRUMENT_TYPE_CONTACT_BASED)
            elif "resolution" in instrument_parameters:
                set_field("instrument_type", INSTRUMENT_TYPE_MICROSCOPE_BASED)
        except:  # noqa: E722
            set_field("instrument_type", INSTRUMENT_TYPE_UNDEFINED)

    # The measurement as it stands after what the file said
    current = dataclasses.replace(
        params,
        **{
            name: fields[name]
            for name in ("data_source", "size_x", "size_y", "unit", "height_scale",
                         "is_periodic", "instrument_name", "instrument_parameters")
            if name in fields
        },
    )

    # Read the file if metadata information is complete
    if not current.is_metadata_complete:
        return

    with timer("metadata is complete"):
        _log.info(f"Metadata of {label} is complete. Generating images.")
        with timer("_read"):
            st_topo = read_topography(reader, current)

        # How much of the original data file is undefined. Both values
        # describe the *measured* data, which is why they are taken from
        # the bottom of the pipeline rather than from `st_topo` itself:
        # with filling enabled the pipeline reports no undefined data by
        # definition, which would erase the very information the fill
        # mode was chosen in response to.
        fraction = undefined_data_fraction(st_topo)
        set_field("undefined_data_fraction", fraction)
        set_field("has_undefined_data", None if fraction is None else fraction > 0)

        # What the detrending actually removed. `st_topo` is the
        # detrended topography, so this reads the fit it performed
        # rather than repeating it.
        set_field("detrend_parameters", detrend_parameters(st_topo))

        # Refresh other cached quantities
        with timer("refresh_bandwidth_cache"):
            fields.update(bandwidth_fields(st_topo))

        for name, (description, _) in _DERIVED_WRITERS.items():
            if name == "deepzoom" and current.size_y is None:
                # Only a map (not a line scan) has deep zoom images
                continue
            with timer(_DERIVED_TIMERS[name]):
                try:
                    result.derived[name] = write_derived(name, st_topo, current, writer)
                except _soft_time_limit_exceeded():
                    # The worker is out of time, which is no fault of the file
                    raise
                except Exception as exc:
                    _log.error(
                        "Problems while generating %s for topography %s: %s. "
                        "Saving <None> instead.",
                        description,
                        label,
                        exc,
                        exc_info=True,
                    )
                    result.derived[name] = None


def missing_derived_files(result: InspectionResult, is_map: bool) -> List[str]:
    """The derived files a complete inspection should have written but did not."""
    if not result.derived:
        # Metadata incomplete: nothing was meant to be generated
        return []
    missing = []
    if not result.derived.get("thumbnail"):
        missing.append("thumbnail")
    # deepzoom is only generated for 2D maps
    if is_map and not result.derived.get("deepzoom"):
        missing.append("deepzoom")
    if not result.derived.get("squeezed_datafile"):
        missing.append("squeezed_datafile")
    return missing
