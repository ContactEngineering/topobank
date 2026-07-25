Measurements and measurement types
==================================

A measurement is one dataset recorded on a specimen. The
:class:`~topobank.manager.models.Measurement` model is deliberately generic: it
holds identity, relations, permissions, files and task state, but it knows nothing
about what kind of data it points at. Everything that *does* depend on the kind of
data - which metadata the measurement has, how its data file is read, which derived
artifacts exist - lives in a **measurement type**.

TopoBank ships three measurement types, all of them height data:

===========================  ===================================================
Kind                         Data
===========================  ===================================================
``topography-map``           Two-dimensional map of surface heights
``uniform-line-scan``        Line scan on a uniform grid
``nonuniform-line-scan``     Line scan with non-uniformly spaced points
===========================  ===================================================

The set of kinds is a runtime registry, not a fixed list, so an external package
can add a kind that is not topography data at all - a spectrum, a force curve -
without any change to TopoBank itself.

How a measurement stores its metadata
-------------------------------------

Instead of one column per metadata field, a measurement carries two JSON documents
plus a discriminator:

``kind``
    The registry key of its measurement type, e.g. ``"topography-map"``. Empty
    until the data file has been inspected. This is the column to filter on.

``metadata``
    The user-facing physical metadata, validated against the type's
    ``Metadata`` schema on every write. Use ``measurement.meta`` for a typed view
    and :meth:`~topobank.manager.models.Measurement.update_metadata` to change it::

        measurement.meta.size_x            # 512.0
        measurement.update_metadata(unit="µm", detrend_mode="height")

``file_info``
    A read-only cache of what was found in the data file: resolution, bandwidths,
    the channel inventory, and which metadata the file leaves up to the user. It is
    written only by the inspection task. Use ``measurement.info`` for a typed view.

Because the schemas are per kind, a field that does not apply to a kind does not
exist on it. A nonuniform line scan supports neither periodicity nor interpolation
of undefined data, so ``NonuniformLineScanMetadata`` has no ``is_periodic`` and no
``fill_undefined_data_mode`` field, and setting either is an error rather than a
value that is silently ignored.

Data channels are identified by name
------------------------------------

A data file can hold several channels, and a measurement refers to exactly one of
them. That reference is a **name**, not a position::

    measurement.channel_name        # 'ZSensor'
    measurement.channel_occurrence  # None

Identifying channels positionally is fragile: if a reader changes the order in
which it reports channels, a stored index silently starts pointing at different
data. With a name, reordering is irrelevant.

Channel names are not guaranteed to be unique within a file, so
``channel_occurrence`` breaks ties. It is a disambiguator rather than part of the
identity, and is recorded **only** when the selected name matches more than one
channel; otherwise it is ``None``. That makes a ``None`` meaningful: it asserts the
name identified exactly one channel when it was selected. If the same name later
matches several, that assertion is violated and the measurement reports an error
instead of resolving to an arbitrary match. Likewise, a name that has vanished is
an error rather than a silent fall back to the file's default channel.

The kind of a measurement follows from its channel, so selecting a different
channel can change the kind - and re-running the inspection is what applies that.
Metadata the new kind also has survives the change; the rest is dropped.

Which channels can be imported
------------------------------

``measurement.info.channels`` lists every channel in the data file, each annotated
with the kind it would be imported as, or ``None`` if no registered type claims it::

    for channel in measurement.info.channels:
        print(channel.name, channel.dim, channel.unit, channel.kind)

Channels that do not hold height data - an amplitude error or phase map next to the
height channel in an AFM file - are listed with ``kind = None`` today. They are not
special-cased as unsupported: registering a measurement type that claims them is
all it takes to make them importable.

Adding a measurement type
-------------------------

Subclass :class:`~topobank.measurements.types.MeasurementType`, declare the schemas,
and register it::

    from topobank.measurements.registry import register_measurement_type
    from topobank.measurements.schemas import MeasurementMetadata, MeasurementFileInfo
    from topobank.measurements.types import MeasurementType


    class SpectrumMetadata(MeasurementMetadata):
        kind: Literal["xps-spectrum"] = "xps-spectrum"
        excitation_energy: Optional[float] = None


    class SpectrumFileInfo(MeasurementFileInfo):
        kind: Literal["xps-spectrum"] = "xps-spectrum"
        nb_points: Optional[int] = None


    @register_measurement_type
    class SpectrumType(MeasurementType):
        class Meta:
            name = "xps-spectrum"      # stored in the database - never rename
            display_name = "XPS spectrum"

        Metadata = SpectrumMetadata
        FileInfo = SpectrumFileInfo

        @classmethod
        def sniff(cls, measurement):
            """Open the data file, or return None if this is not our format."""

        def read(self, measurement, **kwargs):
            """Return the in-memory data object."""

        def inspect(self, measurement, inspection, channel_index):
            """Derive metadata and cached values from the data file."""

The data object that ``read`` returns comes from whatever package is appropriate -
for the built-in kinds that is ``SurfaceTopography``, but nothing in the core
assumes it. Types whose data is not a ``SurfaceTopography`` object leave
``yields_surface_topography`` at ``False``, which keeps them out of operations that
iterate a dataset as a surface container.

``Meta.name`` ends up in the database, in exported containers and in published
datasets. **It must never be renamed once released.**

Registration
~~~~~~~~~~~~

Either register from the ``ready()`` method of your package's ``AppConfig``, or
declare an entry point in the ``topobank.measurement_types`` group:

.. code-block:: toml

    [project.entry-points."topobank.measurement_types"]
    xps = "my_package.measurements:SpectrumType"

An entry point may resolve to a ``MeasurementType`` subclass, which is registered,
or to a module, which is expected to register its own types on import. A plugin that
fails to load is logged and skipped rather than taken down the site with it.

For entry points to be discovered, ``topobank.measurements`` has to be in
``INSTALLED_APPS``::

    INSTALLED_APPS = [
        ...
        "topobank.measurements.apps.MeasurementsAppConfig",
        "topobank.manager.apps.ManagerAppConfig",
        ...
    ]

The three built-in types are registered by the ``manager`` app as well, so they are
available even without this entry; only third-party discovery depends on it.

When a kind is not registered
-----------------------------

If the package providing a kind is uninstalled, its measurements do not disappear.
The records stay listable, downloadable and deletable, and their raw data files stay
intact. What is blocked is anything that needs to interpret the data: reading it,
editing its metadata, and running analyses on it all raise
:class:`~topobank.measurements.registry.UnknownMeasurementKindError`. Re-inspecting
such a measurement determines its kind from the file again, so installing the package
back - or having another type claim the channel - repairs it.

Workflows declare the kinds they support
----------------------------------------

Since one model covers many kinds, the subject's model class no longer says whether
a workflow applies. Workflows that analyze measurements therefore declare which
kinds they handle::

    class Meta:
        implementations = {Measurement: "measurement_implementation", ...}
        supported_kinds = {"topography-map", "uniform-line-scan"}

There is deliberately no wildcard, and omitting ``supported_kinds`` is an error: a
workflow written for height data must not silently claim a kind of measurement that
is added later.
