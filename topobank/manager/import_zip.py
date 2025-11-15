import datetime

import yaml
from django.core.files import File
from django.utils.timezone import now

from ..authorization.models import PermissionSet
from ..files.models import Manifest
from .models import Surface, Topography

TOPOGRAPHY_DEFAULT_ATTR_VALUES = {
    "tags": [],
    "fill_undefined_data_mode": Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING,
    "detrend_mode": "center",
    "is_periodic": False,
    "height_scale": 1.0,
    "data_source": 0,
    "measurement_date": datetime.date(1970, 1, 1),
    "description": "",
}

SURFACE_DEFAULT_ATTR_VALUES = {
    "tags": [],
    "description": "",
    "is_published": False,
}


def import_measurement(topo_dict, topo_file, surface, ignore_missing=False):
    """
    Process a single topography from a surface container ZIP.

    Parameters
    ----------
    topo_dict : dict
        Dictionary with metadata of the topography.
    topo_file : file
        File object with the topography data.
    surface : Surface
        Surface instance to which the topography belongs.
    ignore_missing : bool, optional
        If True, try to find reasonable defaults for missing attributes.
        (Default: False)
    """
    topo_name = topo_dict["name"]

    size_x, *size_rest = topo_dict["size"]
    size_y = None if len(size_rest) == 0 else size_rest[0]

    user = surface.created_by

    if ignore_missing:
        for k, default in TOPOGRAPHY_DEFAULT_ATTR_VALUES.items():
            topo_dict.setdefault(k, default)

    topo_kwargs = dict(
        created_by=user,
        name=topo_name,
        surface=surface,
        size_x=size_x,
        size_y=size_y,
        measurement_date=topo_dict["measurement_date"],
        description=topo_dict["description"],
        data_source=topo_dict["data_source"],
        unit=topo_dict["unit"],
        tags=topo_dict["tags"],
        fill_undefined_data_mode=topo_dict["fill_undefined_data_mode"],
        detrend_mode=topo_dict["detrend_mode"],
        is_periodic=topo_dict["is_periodic"],
    )

    try:
        topo_kwargs.update(
            dict(
                instrument_name=topo_dict["instrument"]["name"],
                instrument_type=topo_dict["instrument"]["type"],
                instrument_parameters=topo_dict["instrument"]["parameters"],
            )
        )
    except KeyError:
        # Metadata does not contain instrument information
        pass

    try:
        topo_kwargs["height_scale"] = topo_dict["height_scale"]
    except KeyError:
        # If height_scale is not included, it will probably already
        # applied because of file contents while loading
        pass

    topography = Topography(**topo_kwargs)
    topography.datafile = Manifest.objects.create(
        permissions=surface.permissions, filename=topo_name, created_by=user, folder=None
    )
    topography.datafile.save_file(File(topo_file))
    # We need to save again to store the new file name
    topography.save()


def import_container_zip(
    surface_zip,
    user,
    datafile_attribute="datafile",
    ignore_missing=False,
    unsafe_yaml_loader=False,
    tag=None,
):
    """
    Import surfaces from a ZIP archive and create corresponding Surface instances in the database.

    This function processes a ZIP archive containing surface data, including metadata and topography files. It creates
    Surface instances for each surface in the archive, sets created_by to the specified user, and imports topographies
    associated with each surface. It also handles optional tagging of surfaces, setting of default values for missing
    attributes, and the choice between safe and unsafe YAML loading for metadata.

    Parameters
    ----------
    surface_zip : zipfile.ZipFile
        The ZIP archive containing surfaces and their metadata.
    user : topobank.users.models.User
        The user who will be set as created_by of the imported surfaces.
    datafile_attribute : str, optional
        The attribute name in the metadata file that stores the file name for a topography's data file.
        Default is 'datafile'.
    ignore_missing : bool, optional
        If True, the function will try to find reasonable defaults for missing attributes in the metadata.
        Default is False.
    unsafe_yaml_loader : bool, optional
        If True, an unsafe YAML loader will be used to load the metadata. This can potentially execute
        malicious code contained in the YAML file, so it should be used with caution. Default is False.
    tag : str, optional
        An optional tag to add to all imported surfaces. Default is None.

    Returns
    -------
    list of Surface
        A list of the Surface instances that were created as a result of the import.

    Notes
    -----
    The function assumes the ZIP archive's structure and metadata format are correct and does not perform
    extensive validation of the archive's contents.
    """
    surfaces = []
    with surface_zip.open("meta.yml", mode="r") as meta_file:
        yaml_loader = yaml.full_load if unsafe_yaml_loader else yaml.safe_load
        meta = yaml_loader(meta_file)

        for surface_dict in meta["surfaces"]:
            if ignore_missing:
                for k, default in SURFACE_DEFAULT_ATTR_VALUES.items():
                    surface_dict.setdefault(k, default)

            import_time = str(now())

            surface_description = surface_dict["description"]
            surface_description += (
                f'\n\nImported from file "{surface_zip.filename}" on {import_time}.'
            )
            tags = set(surface_dict["tags"])
            if tag is not None:
                tags.add(tag)
            surface = Surface.objects.create(
                created_by=user,
                name=surface_dict["name"],
                category=surface_dict["category"],
                description=surface_description,
                tags=tags,
                permissions=PermissionSet.objects.create(),
            )
            surface.save()
            surface.permissions.grant_for_user(user, "full")

            # WARNING: Does this need to be updated to new property API??
            if "properties" in surface_dict:
                from topobank.properties.models import Property

                for property_dict in surface_dict["properties"]:
                    name = property_dict["name"]
                    value = property_dict["value"]
                    unit = property_dict.get("unit", None)
                    Property.objects.create(
                        surface=surface, name=name, value=value, unit=unit
                    )
                surface.save()

            surfaces += [surface]

            for topo_idx, topo_dict in enumerate(surface_dict["topographies"]):
                datafile_name = topo_dict[datafile_attribute][
                    "original"
                ]  # we just import the original
                topo_file = surface_zip.open(datafile_name, mode="r")

                import_measurement(
                    topo_dict, topo_file, surface, ignore_missing=ignore_missing
                )

    return surfaces
