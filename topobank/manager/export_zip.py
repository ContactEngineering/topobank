"""
Import and export surfaces through archives aka "surface containers".
"""

import json
import logging
import math
import os.path
import textwrap
import zipfile

import SurfaceTopography
from django.conf import settings
from django.utils.text import slugify
from django.utils.timezone import now

import topobank
from topobank.supplib.json import ExtendedJSONEncoder

from .container_schema import CONTAINER_METADATA_FILENAME, ContainerMeta

_log = logging.getLogger(__name__)


def export_container_zip(file, surfaces, extra_metadata=None):
    """
    Write container data to a file.

    Parameters
    ----------
    file: File like object
        Should be opened in "w" mode.
    surfaces: sequence of Surface instances
        Surface which should be included in container.
    extra_metadata: dict, optional
        Opaque, optional container-level metadata that is written verbatim to
        the ``extra`` key of the metadata file. TopoBank does not interpret it;
        it lets callers (e.g. the SDS API) attach extra information such as
        training-group membership. Any surface references therein should use
        indices into ``surfaces``. (Default: None)

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

        topographies = surface.topography_set.all()

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
    # ``index.json`` is the single source of truth for container metadata. We
    # build it through the pydantic schema, which validates the structure and
    # normalizes the layout (``exclude_none`` drops absent optional fields such
    # as an author's ``orcid`` or a missing squeezed data file).
    metadata = ContainerMeta(
        versions=dict(topobank=topobank.__version__),
        surfaces=surfaces_dicts,
        created_at=str(now()),
        extra=extra_metadata,
    )

    zf.writestr(
        CONTAINER_METADATA_FILENAME,
        json.dumps(
            metadata.model_dump(by_alias=True, exclude_none=True),
            indent=4,
            cls=ExtendedJSONEncoder,
        ),
    )

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
    found in the auxiliary file 'index.json'. It is formatted as
    [JSON](https://www.json.org/) file.

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
