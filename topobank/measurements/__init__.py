"""
Measurement types and their metadata schemas.

A measurement stored in the database is a thin record: identity, relations,
files, task state, plus a ``kind`` and two JSON documents holding its metadata.
Everything that depends on *what kind* of measurement it is lives here, in a
registry of measurement types.

Adding a new kind of measurement - a spectrum, a force curve, something that is
not topography data at all - means registering a
:class:`~topobank.measurements.types.MeasurementType` that declares its pydantic
schemas and knows how to read its data. External packages can do this through the
``topobank.measurement_types`` entry-point group without any change to the core.
"""
