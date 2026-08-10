import yaml
from django.core.files import File
from django.utils.timezone import now

from ..authorization import get_permission_model
from ..files.models import Manifest
from .container_schema import (
    CONTAINER_METADATA_FILENAME,
    LEGACY_METADATA_FILENAME,
    ContainerMeta,
    MeasurementMeta,
)
from .models import Measurement, Surface


def load_container_metadata(surface_zip, unsafe_yaml_loader=False) -> ContainerMeta:
    """
    Load and validate the metadata of a surface container.

    The canonical metadata file is ``index.json``. For backward compatibility
    with archives produced by older versions of TopoBank, a legacy ``meta.yml``
    file is accepted as a fallback. In both cases the metadata is validated
    against (and returned as) a :class:`ContainerMeta` instance.

    Parameters
    ----------
    surface_zip : zipfile.ZipFile
        The container archive.
    unsafe_yaml_loader : bool, optional
        If True, use an unsafe YAML loader when reading the legacy ``meta.yml``.
        This can execute malicious code contained in the YAML file and should be
        used with caution. (Default: False)

    Returns
    -------
    ContainerMeta
        The validated container metadata.
    """
    names = set(surface_zip.namelist())
    if CONTAINER_METADATA_FILENAME in names:
        with surface_zip.open(CONTAINER_METADATA_FILENAME, mode="r") as f:
            return ContainerMeta.model_validate_json(f.read())
    if LEGACY_METADATA_FILENAME in names:
        with surface_zip.open(LEGACY_METADATA_FILENAME, mode="r") as f:
            yaml_loader = yaml.full_load if unsafe_yaml_loader else yaml.safe_load
            return ContainerMeta.model_validate(yaml_loader(f))
    raise RuntimeError(
        f"Container archive contains neither '{CONTAINER_METADATA_FILENAME}' nor "
        f"'{LEGACY_METADATA_FILENAME}'; cannot determine its contents."
    )


def import_measurement(measurement_meta: MeasurementMeta, measurement_file, surface):
    """
    Create a single measurement from a surface container.

    Parameters
    ----------
    measurement_meta : MeasurementMeta
        Validated metadata of the measurement.
    measurement_file : file
        File object with the measurement data.
    surface : Surface
        Surface instance to which the measurement belongs.
    """
    user = surface.created_by

    measurement = Measurement(
        created_by=user,
        name=measurement_meta.name,
        surface=surface,
        measurement_date=measurement_meta.measurement_date,
        description=measurement_meta.description,
        tags=measurement_meta.tags,
        # Handles both the current and the legacy container layout.
        **measurement_meta.to_measurement_kwargs(),
    )
    measurement.datafile = Manifest.objects.create(
        permissions=surface.permissions,
        filename=measurement_meta.name,
        created_by=user,
    )
    measurement.datafile.save_file(File(measurement_file))
    # We need to save again to store the new file name
    measurement.save()


def import_container_zip(
    surface_zip,
    user,
    ignore_missing=False,
    unsafe_yaml_loader=False,
    tag=None,
):
    """
    Import surfaces from a ZIP archive and create corresponding Surface instances in the database.

    This function processes a ZIP archive containing surface data, including metadata and measurement files. It creates
    Surface instances for each surface in the archive, sets created_by to the specified user, and imports measurements
    associated with each surface. It also handles optional tagging of surfaces.

    The metadata is loaded and validated through the :class:`ContainerMeta` schema, which preferentially reads the
    canonical ``index.json`` and falls back to the legacy ``meta.yml``. Missing optional attributes are filled with the
    schema's defaults, so ``ignore_missing`` is kept only for backward compatibility and no longer changes behavior.

    Parameters
    ----------
    surface_zip : zipfile.ZipFile
        The ZIP archive containing surfaces and their metadata.
    user : topobank.users.models.User
        The user who will be set as created_by of the imported surfaces.
    ignore_missing : bool, optional
        Deprecated and ignored; defaults for missing attributes are now supplied by the schema. Default is False.
    unsafe_yaml_loader : bool, optional
        If True, an unsafe YAML loader will be used to load a legacy ``meta.yml``. This can potentially execute
        malicious code contained in the YAML file, so it should be used with caution. Default is False.
    tag : str, optional
        An optional tag to add to all imported surfaces. Default is None.

    Returns
    -------
    list of Surface
        A list of the Surface instances that were created as a result of the import.

    Notes
    -----
    The function assumes the ZIP archive's structure is correct and does not perform extensive validation of the
    archive's contents beyond the metadata schema.
    """
    meta = load_container_metadata(surface_zip, unsafe_yaml_loader=unsafe_yaml_loader)

    surfaces = []
    import_time = str(now())

    for surface_meta in meta.surfaces:
        surface_description = surface_meta.description
        surface_description += (
            f'\n\nImported from file "{surface_zip.filename}" on {import_time}.'
        )
        tags = set(surface_meta.tags)
        if tag is not None:
            tags.add(tag)
        surface = Surface.objects.create(
            created_by=user,
            name=surface_meta.name,
            category=surface_meta.category,
            description=surface_description,
            tags=tags,
            permissions=get_permission_model().objects.create(),
        )
        surface.save()
        surface.permissions.grant_for_user(user, "full")

        if surface_meta.properties:
            from topobank.properties.models import Property

            for property_meta in surface_meta.properties:
                Property.objects.create(
                    surface=surface,
                    name=property_meta.name,
                    value=property_meta.value,
                    unit=property_meta.unit,
                )
            surface.save()

        surfaces.append(surface)

        for measurement_meta in surface_meta.measurements:
            # We just import the original data file.
            measurement_file = surface_zip.open(
                measurement_meta.datafile.original, mode="r"
            )
            import_measurement(measurement_meta, measurement_file, surface)

    return surfaces
