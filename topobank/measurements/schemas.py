"""
Pydantic schemas for measurement metadata.

These schemas take over the role that typed Django columns played before: they
define which metadata a measurement of a given kind has, its types, defaults and
validators. There are two families:

``MeasurementMetadata``
    User-facing physical metadata, edited through the API and validated on every
    write. Stored in ``Measurement.metadata``.

``MeasurementFileInfo``
    Read-only, file-derived cache written exclusively by the inspection task.
    Stored in ``Measurement.file_info``.

Both carry a ``kind`` discriminator so that the stored JSON is self-describing
(important for exported containers and published datasets, which must be
readable without a database row at hand).

Fields that do *not* affect derived data (thumbnails, cached files, analyses)
are marked with ``json_schema_extra={"significant": False}``; see
:func:`significant_values`.
"""

import logging
from typing import Annotated, Literal, Optional, Union

import pydantic
from SurfaceTopography.Metadata import InstrumentParametersModel

_log = logging.getLogger(__name__)

#
# Choices. These mirror the ``*_CHOICES`` lists that used to live on the Django
# model. They are part of the schema now, so a kind that does not support an
# option simply does not have the field.
#

#: Length units offered for lateral and height data. ``pm`` is the default unit
#: of VK files, so it has to be part of the list.
LengthUnit = Literal["km", "m", "mm", "µm", "nm", "Å", "pm"]

DetrendMode = Literal["center", "height", "curvature"]

FillUndefinedDataMode = Literal["do-not-fill", "harmonic"]

InstrumentType = Literal["undefined", "microscope-based", "contact-based"]

#: Human-readable descriptions of the detrend modes, for UI use.
DETREND_MODE_DESCRIPTIONS = {
    "center": "No detrending, but subtract mean height",
    "height": "Remove tilt",
    "curvature": "Remove curvature and tilt",
}

#: Human-readable descriptions of the undefined-data fill modes, for UI use.
FILL_UNDEFINED_DATA_MODE_DESCRIPTIONS = {
    "do-not-fill": "Do not fill undefined data points",
    "harmonic": "Interpolate undefined data points with harmonic functions",
}

#: Human-readable descriptions of the instrument types, for UI use.
INSTRUMENT_TYPE_DESCRIPTIONS = {
    "undefined": "Instrument of unknown type - all data considered as reliable",
    "microscope-based": "Microscope-based instrument with known resolution",
    "contact-based": "Contact-based instrument with known tip radius",
}

#: Human-readable descriptions of the possible values of
#: ``MeasurementFileInfo.has_undefined_data``.
HAS_UNDEFINED_DATA_DESCRIPTION = {
    None: (
        "contact.engineering could not (yet) determine if this measurement has "
        "undefined data points."
    ),
    True: "The dataset has undefined/missing data points.",
    False: "No undefined/missing data found.",
}


def _insignificant(**kwargs):
    """Field that does not affect derived data (see :func:`significant_values`)."""
    extra = kwargs.pop("json_schema_extra", {})
    return pydantic.Field(**kwargs, json_schema_extra={**extra, "significant": False})


def significant_values(model):
    """
    Return the values of a model that affect derived data.

    Changing one of these invalidates thumbnails, cached files and analyses, so
    the model's ``save`` compares this mapping between the old and the new
    metadata to decide whether a refresh is needed. Fields marked
    ``significant: False`` (such as the free-text instrument name) are skipped;
    nested models are handled recursively.

    Parameters
    ----------
    model : pydantic.BaseModel
        Metadata instance.

    Returns
    -------
    dict
        Mapping of field name to value, with insignificant fields removed.
    """
    values = {}
    for name, field in type(model).model_fields.items():
        extra = field.json_schema_extra or {}
        if extra.get("significant") is False:
            continue
        value = getattr(model, name)
        if isinstance(value, pydantic.BaseModel):
            values[name] = significant_values(value)
        else:
            values[name] = value
    return values


def dump_metadata(model):
    """
    Serialize a metadata or file-info model for storage in a JSON field.

    ``exclude_none`` is not cosmetic: ``InstrumentParametersModel`` (which comes
    from SurfaceTopography) annotates its fields as non-optional while defaulting
    them to ``None``, so pydantic accepts the default but rejects an explicit
    ``None`` on the way back in. Dumping without ``exclude_none`` would therefore
    produce documents that cannot be re-read. Every field of these schemas has a
    default, so omitting the ones that are None loses nothing.

    Parameters
    ----------
    model : pydantic.BaseModel
        Metadata or file-info instance.

    Returns
    -------
    dict
        JSON-serializable document.
    """
    return model.model_dump(mode="json", exclude_none=True)


def coerce_metadata(schema, values):
    """
    Build a metadata instance of `schema`, keeping whatever `values` fit.

    Used when a measurement's kind changes - for instance when the user selects a
    channel of a different dimensionality - so that metadata the user has
    adjusted survives wherever the new kind has a corresponding field. Values
    that the target schema does not know, or that it rejects, fall back to the
    schema's default.

    Parameters
    ----------
    schema : type
        Subclass of :class:`MeasurementMetadata`.
    values : dict
        Previously stored metadata.

    Returns
    -------
    MeasurementMetadata
        Instance of `schema`.
    """
    instance = schema()
    for name, value in (values or {}).items():
        if name == "kind" or name not in schema.model_fields:
            # Not applicable to this kind; deliberately dropped.
            continue
        try:
            setattr(instance, name, value)
        except (pydantic.ValidationError, ValueError):
            _log.debug(
                "Dropping metadata %s=%r, which %s does not accept.",
                name,
                value,
                schema.__name__,
            )
    return instance


#
# Metadata
#


class InstrumentMetadata(pydantic.BaseModel):
    """Instrument used to acquire a measurement."""

    model_config = pydantic.ConfigDict(extra="forbid")

    #: Free-text label. Purely descriptive, so a change does not invalidate
    #: anything derived from the data.
    name: str = _insignificant(default="")
    type: InstrumentType = "undefined"
    parameters: InstrumentParametersModel = pydantic.Field(
        default_factory=InstrumentParametersModel
    )


class MeasurementMetadata(pydantic.BaseModel):
    """
    Base class for the user-facing metadata of a measurement.

    Subclasses pin ``kind`` to a literal and add the fields that apply to that
    kind. ``extra="forbid"`` means a field that does not apply to a kind is
    rejected rather than silently stored.
    """

    model_config = pydantic.ConfigDict(extra="forbid", validate_assignment=True)

    kind: str
    instrument: InstrumentMetadata = pydantic.Field(
        default_factory=InstrumentMetadata
    )

    def missing_metadata(self) -> list[str]:
        """
        Human-readable names of the metadata still required to read the file.

        A field counts as missing only if neither the data file nor the stored
        metadata provides it, because the inspection merges the file's values in
        before this is evaluated.
        """
        return []

    def is_complete(self) -> bool:
        """
        Whether the data file can be read with this metadata.

        The inspection task only generates derived artifacts once this is True.
        """
        return not self.missing_metadata()


class HeightMetadata(MeasurementMetadata):
    """
    Common metadata of the height-data kinds.

    Not registered itself; shared by topography maps and line scans.
    """

    #: Lateral size along x. ``None`` until the file or the user provides it.
    size_x: Optional[float] = pydantic.Field(default=None, ge=0)
    #: Unit of both the lateral sizes and the heights.
    unit: Optional[LengthUnit] = None
    #: Factor applied to the raw values to obtain heights in ``unit``.
    height_scale: float = 1.0
    detrend_mode: DetrendMode = "center"

    def missing_metadata(self) -> list[str]:
        missing = []
        if self.size_x is None:
            missing.append("physical size")
        if self.unit is None:
            missing.append("unit")
        if self.height_scale is None:
            missing.append("height scale")
        return missing


class TopographyMapMetadata(HeightMetadata):
    """Metadata of a two-dimensional height map."""

    kind: Literal["topography-map"] = "topography-map"

    #: Lateral size along y. Always set for a map.
    size_y: Optional[float] = pydantic.Field(default=None, ge=0)
    is_periodic: bool = False
    fill_undefined_data_mode: FillUndefinedDataMode = "do-not-fill"

    def missing_metadata(self) -> list[str]:
        missing = super().missing_metadata()
        if self.size_y is None and "physical size" not in missing:
            missing.append("physical size")
        return missing


class UniformLineScanMetadata(HeightMetadata):
    """Metadata of a line scan on a uniform grid."""

    kind: Literal["uniform-line-scan"] = "uniform-line-scan"

    is_periodic: bool = False
    fill_undefined_data_mode: FillUndefinedDataMode = "do-not-fill"


class NonuniformLineScanMetadata(HeightMetadata):
    """
    Metadata of a line scan with non-uniformly spaced points.

    Such a line scan supports neither periodicity nor interpolation of undefined
    data, so - unlike the two kinds above - it has no ``is_periodic`` and no
    ``fill_undefined_data_mode`` field at all. What used to be expressed by
    setting ``is_periodic_editable = False`` at runtime is structural here.
    """

    kind: Literal["nonuniform-line-scan"] = "nonuniform-line-scan"


#
# File info
#


class ChannelInfo(pydantic.BaseModel):
    """
    One data channel of a measurement's data file.

    The list of these is the inventory the UI offers for channel selection. Each
    entry also records the measurement kind the channel would be imported as, or
    ``None`` if no registered measurement type claims it.
    """

    model_config = pydantic.ConfigDict(extra="forbid")

    #: Channel name as reported by the reader. Together with ``occurrence`` this
    #: identifies the channel; the position in this list is irrelevant.
    name: str
    #: Tie-breaker for files that contain several channels of the same name.
    #: ``None`` whenever the name is unique within the file.
    occurrence: Optional[int] = None
    #: Number of dimensions of the data (1 for line scans, 2 for maps).
    dim: Optional[int] = None
    #: Lateral unit.
    unit: Optional[str] = None
    #: Unit of the data itself, for channels that do not contain heights.
    data_unit: Optional[str] = None
    #: Measurement kind this channel is imported as, or None if unsupported.
    kind: Optional[str] = None

    @property
    def is_supported(self) -> bool:
        """Whether a registered measurement type claims this channel."""
        return self.kind is not None


class MeasurementFileInfo(pydantic.BaseModel):
    """
    Base class for the file-derived cache of a measurement.

    Written exclusively by the inspection task, never by the user.
    """

    model_config = pydantic.ConfigDict(extra="forbid", validate_assignment=True)

    kind: str
    #: Inventory of all channels in the data file, not just the selected one.
    channels: list[ChannelInfo] = pydantic.Field(default_factory=list)


class HeightFileInfo(MeasurementFileInfo):
    """Common file-derived cache of the height-data kinds."""

    #: Number of grid points along x.
    resolution_x: Optional[int] = pydantic.Field(default=None, ge=0)
    #: Lower end of the bandwidth, in meters.
    bandwidth_lower: Optional[float] = None
    #: Upper end of the bandwidth, in meters.
    bandwidth_upper: Optional[float] = None
    #: Shortest reliable wavelength, in meters.
    short_reliability_cutoff: Optional[float] = None
    #: None while undetermined.
    has_undefined_data: Optional[bool] = None

    #
    # Which metadata the file leaves up to the user. These describe what the
    # *file* provides, which is why they live here rather than in the metadata.
    #
    size_editable: bool = False
    unit_editable: bool = False
    height_scale_editable: bool = False
    is_periodic_editable: bool = True

    def get_undefined_data_status(self, fill_undefined_data_mode=None) -> str:
        """Human-readable description of the undefined-data status."""
        s = HAS_UNDEFINED_DATA_DESCRIPTION[self.has_undefined_data]
        if fill_undefined_data_mode == "do-not-fill":
            s += " No correction of undefined data is performed."
        elif fill_undefined_data_mode == "harmonic":
            s += (
                " Undefined/missing values are filled in with values obtained "
                "from a harmonic interpolation."
            )
        return s


class TopographyMapFileInfo(HeightFileInfo):
    """File-derived cache of a two-dimensional height map."""

    kind: Literal["topography-map"] = "topography-map"

    #: Number of grid points along y.
    resolution_y: Optional[int] = pydantic.Field(default=None, ge=0)


class UniformLineScanFileInfo(HeightFileInfo):
    """File-derived cache of a uniform line scan."""

    kind: Literal["uniform-line-scan"] = "uniform-line-scan"


class NonuniformLineScanFileInfo(HeightFileInfo):
    """File-derived cache of a nonuniform line scan."""

    kind: Literal["nonuniform-line-scan"] = "nonuniform-line-scan"

    #: A nonuniform line scan is never periodic.
    is_periodic_editable: bool = False


#
# Discriminated unions, for parsing metadata without a database row at hand
# (container import, published datasets).
#

BuiltinMetadata = Annotated[
    Union[TopographyMapMetadata, UniformLineScanMetadata, NonuniformLineScanMetadata],
    pydantic.Field(discriminator="kind"),
]

BuiltinFileInfo = Annotated[
    Union[TopographyMapFileInfo, UniformLineScanFileInfo, NonuniformLineScanFileInfo],
    pydantic.Field(discriminator="kind"),
]
