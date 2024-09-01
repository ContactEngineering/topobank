"""
Import and export surfaces through archives aka "surface containers".
"""

import datetime
import json
import logging
import math
import os.path
import textwrap
import zipfile

import SurfaceTopography
import yaml
from django.conf import settings
from django.core.files import File
from django.utils.text import slugify
from django.utils.timezone import now

import topobank

from ..files.models import Manifest
from .models import Property, Surface, Topography

_log = logging.getLogger(__name__)

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


def import_topography(topo_dict, topo_file, surface, ignore_missing=False):
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

    user = surface.creator

    if ignore_missing:
        for k, default in TOPOGRAPHY_DEFAULT_ATTR_VALUES.items():
            topo_dict.setdefault(k, default)

    topo_kwargs = dict(
        creator=user,
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
        permissions=surface.permissions, filename=topo_name, uploaded_by=user
    )
    topography.datafile.save_file(File(topo_file))
    # We need to save again to store the new file name
    topography.save()


def import_container(
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
    Surface instances for each surface in the archive, sets the creator to the specified user, and imports topographies
    associated with each surface. It also handles optional tagging of surfaces, setting of default values for missing
    attributes, and the choice between safe and unsafe YAML loading for metadata.

    Parameters
    ----------
    surface_zip : zipfile.ZipFile
        The ZIP archive containing surfaces and their metadata.
    user : topobank.users.models.User
        The user who will be set as the creator of the imported surfaces.
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
            surface = Surface(
                creator=user,
                name=surface_dict["name"],
                category=surface_dict["category"],
                description=surface_description,
                tags=tags,
            )
            surface.save()

            if "properties" in surface_dict:
                for property_dict in surface_dict["properties"]:
                    name = property_dict["name"]
                    value = property_dict["value"]
                    unit = property_dict.get("unit", None)
                    surface.properties.add(Property(name=name, value=value, unit=unit))
                surface.save()

            surfaces += [surface]

            for topo_idx, topo_dict in enumerate(surface_dict["topographies"]):
                datafile_name = topo_dict[datafile_attribute][
                    "original"
                ]  # we just import the original
                topo_file = surface_zip.open(datafile_name, mode="r")

                import_topography(
                    topo_dict, topo_file, surface, ignore_missing=ignore_missing
                )

    return surfaces


def write_surface_container(file, surfaces):
    """
    Write container data to a file.

    Parameters
    ----------
    file: File like object
        Should be opened in "w" mode.
    surfaces: sequence of Surface instances
        Surface which should be included in container.

    Returns
    -------
    None
    """
    surfaces_dicts = []

    publications = (
        set()
    )  # collect publications so we can list the licenses in an extra file

    zf = zipfile.ZipFile(file, mode="w")

    #
    # Add meta data and topography files for all given surfaces
    #
    nb_surfaces = len(surfaces)
    log10_nb_surfaces = int(math.log10(nb_surfaces)) if nb_surfaces > 0 else 0
    for surface_index, surface in enumerate(surfaces):
        surface_prefix = (
            ""
            if nb_surfaces == 1
            else f"{surface_index}".zfill(log10_nb_surfaces + 1) + "-"
        )

        topographies = Topography.objects.filter(surface=surface)

        topography_dicts = []

        # create unique file names for the data files
        # using the original file name + a counter, if needed

        nb_topographies = len(topographies)
        log10_nb_topographies = (
            int(math.log10(nb_topographies)) if nb_topographies > 0 else 0
        )
        for topography_index, topography in enumerate(topographies):
            topography_prefix = (
                f"{topography_index}".zfill(log10_nb_topographies + 1) + "-"
            )

            topo_dict = topography.to_dict()
            # this dict may be okay, but have to check whether the filename is unique
            # because every filename should only appear once in the archive

            #
            # Return original datafile to archive
            #

            # Split out original extension
            _, original_extension = os.path.splitext(topo_dict["datafile"]["original"])
            slugified_name = slugify(topo_dict["name"])
            # `slugified_name` may have an extension since initial `name` is filename
            name, slugified_extension = os.path.splitext(slugified_name)
            if slugified_extension == original_extension:
                # We will add the extension later, hence `slugified_name` should not contain it
                slugified_name = name
            else:
                # Apparently the `name` was not a filename and we need to add the extension
                slugified_extension = original_extension
            # Construct filename for use within the container (note: extension contains the leading '.')
            name_in_container = f"{surface_prefix}{topography_prefix}{slugified_name}{slugified_extension}"
            topo_dict["datafile"]["original"] = name_in_container

            # add topography file to ZIP archive
            zf.writestr(name_in_container, topography.datafile.read())

            #
            # Also add squeezed netcdf file, if possible
            #
            if topography.squeezed_datafile:
                squeezed_name_in_container = (
                    f"{surface_prefix}{topography_prefix}{slugified_name}-squeezed.nc"
                )
                topo_dict["datafile"]["squeezed-netcdf"] = squeezed_name_in_container

                # add topography file to ZIP archive
                zf.writestr(
                    squeezed_name_in_container, topography.squeezed_datafile.read()
                )

            topography_dicts.append(topo_dict)

        surface_dict = surface.to_dict()
        surface_dict["topographies"] = topography_dicts

        surfaces_dicts.append(surface_dict)

        if surface.is_published:
            publications.add(surface.publication)

    #
    # Add metadata file
    #
    metadata = dict(
        versions=dict(topobank=topobank.__version__),
        surfaces=surfaces_dicts,
        creation_time=str(now()),
    )

    zf.writestr("meta.yml", yaml.dump(metadata))

    #
    # Add a Readme file and license files
    #
    readme_txt = textwrap.dedent(
        f"""
    Contents of this ZIP archive
    ============================
    This archive contains {len(surfaces)} digital surface twin(s). Each digital surface
    twin is a collection of individual topography measurements. In total,
    this archive contains {sum(s.topography_set.count() for s in surfaces)} topography measurements.

    There are two files for each measurement:
    - The original data file which was uploaded by a user,
    - as alternative, a NetCDF 3 file with extension "-squeezed.nc" which can
      be used to load the data in other programs, e.g. Matlab or Python. Here,
      "squeezed" means that the measurement was preprocessed: It was rescaled
      according to the height scale factor, was detrended (if selected) and
      missing data points were filled in (if selected).

    The metadata for the digital twins and the individual measurements can be
    found in the auxiliary file 'meta.yml'. It is formatted as
    [YAML](https://yaml.org/) file.

    Version information
    ===================

    TopoBank: {topobank.__version__}
    SurfaceTopography: {SurfaceTopography.__version__}
    """
    )

    if len(publications) > 0:
        #
        # Add datacite_json
        #
        for pub in publications:
            if pub.doi_name:
                zf.writestr(
                    f"other/datacite-{pub.short_url}.json",
                    json.dumps(pub.datacite_json),
                )

        #
        # Add license information to README
        #
        licenses_used = set(pub.license for pub in publications)
        legalcode_filepath = {pub.license: pub.get_license_legalcode_filepath()}
        readme_txt += textwrap.dedent(
            """
        License information
        ===================

        Some surfaces have been published under the following
        licenses, please look at the metadata for each surface
        for the specific license:

        """
        )

        for license in licenses_used:
            license_file_in_archive = f"LICENSE-{license}.txt"
            license_info = settings.CC_LICENSE_INFOS[license]
            readme_txt += textwrap.dedent(
                """
            {}
            {}
            For details about this license see
            - '{}' (description), or
            - '{}' (legal code), or
            - the included file '{}' (legal code).
            """.format(
                    license_info["title"],
                    "-" * len(license_info["title"]),
                    license_info["description_url"],
                    license_info["legal_code_url"],
                    license_file_in_archive,
                )
            )
            #
            # Also add license file
            #
            zf.write(legalcode_filepath[license], arcname=license_file_in_archive)

    zf.writestr("README.txt", textwrap.dedent(readme_txt))

    zf.close()
