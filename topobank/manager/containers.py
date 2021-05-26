"""
Import and export surfaces through archives aka "surface containers".
"""
import zipfile
import os.path
import yaml
import textwrap
import logging

from django.utils.timezone import now
from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage

from .models import Topography

_log = logging.getLogger(__name__)


def write_surface_container(file, surfaces, request=None):
    """Write container data to a file.

    Parameters
    ----------
    file: File like object
        Should be opened in "w" mode.
    surfaces: sequence of Surface instances
        Surface which should be included in container.
    request: HTTPRequest
        If None, urls of published surfaces will only be relative.

    Returns
    -------
    None
    """
    surfaces_dicts = []
    already_used_topofile_names = []
    counter = 0

    publications = set()  # collect publications so we can list the licenses in an extra file

    zf = zipfile.ZipFile(file, mode='w')

    #
    # Add meta data and topography files for all given surfaces
    #
    for surface in surfaces:
        topographies = Topography.objects.filter(surface=surface)

        topography_dicts = []

        # create unique file names for the data files
        # using the original file name + a counter, if needed

        for topography in topographies:
            topo_dict = topography.to_dict()
            # this dict may be okay, but have to check whether the filename is unique
            # because every filename should only appear once in the archive

            def unique_topography_filename(fn):
                """Make sure the filename is unique in archive.

                If filename `fn` is already used, add a counter.
                Return the name that should be used.
                """
                nonlocal counter
                if fn in already_used_topofile_names:
                    fn_root, fn_ext = os.path.splitext(fn)
                    fn = f"{fn_root}_{counter}.{fn_ext}"
                    counter += 1
                return fn

            #
            # Return original datafile to archive
            #
            original_name = unique_topography_filename(
                os.path.basename(topo_dict['datafile']['original'])
            )
            topo_dict['datafile']['original'] = original_name
            already_used_topofile_names.append(original_name)

            # add topography file to ZIP archive
            zf.writestr(original_name, topography.datafile.read())
            #
            # Also add squeezed netcdf file, if possible
            #
            if not topography.has_squeezed_datafile:
                try:
                    topography.renew_squeezed_datafile()
                except Exception as exc:
                    _log.error(f"Cannot generate squeezed datafile of topography id {topography.id} "
                               f"for download: {exc}")
            if topography.has_squeezed_datafile:
                squeezed_file_name = unique_topography_filename(
                    os.path.basename(topo_dict['datafile']['squeezed-netcdf'])
                )
                topo_dict['datafile']['squeezed-netcdf'] = squeezed_file_name
                already_used_topofile_names.append(squeezed_file_name)

                # add topography file to ZIP archive
                zf.writestr(squeezed_file_name, topography.squeezed_datafile.read())

            topography_dicts.append(topo_dict)

        surface_dict = surface.to_dict(request)
        surface_dict['topographies'] = topography_dicts

        surfaces_dicts.append(surface_dict)

        if surface.is_published:
            publications.add(surface.publication)

    #
    # Add metadata file
    #
    metadata = dict(
        versions=dict(topobank=settings.TOPOBANK_VERSION),
        surfaces=surfaces_dicts,
        creation_time=str(now()),
    )

    zf.writestr("meta.yml", yaml.dump(metadata))

    #
    # Add a Readme file and license files
    #
    readme_txt = textwrap.dedent("""
    Contents of this ZIP archive
    ============================
    This archive contains {} surface(s). Each surface is a
    collection of individual topography measurements.
    In total {} topography measurements are included.

    The meta data for the surfaces and the individual topographies
    can be found in the auxiliary file 'meta.yml'. It is formatted
    as a [YAML](https://yaml.org/) file.

    Version information
    ===================

    TopoBank: {}
    """.format(len(surfaces), sum(s.topography_set.count() for s in surfaces),
               settings.TOPOBANK_VERSION))

    if len(publications) > 0:

        licenses_used = set(pub.license for pub in publications)
        readme_txt += textwrap.dedent("""
        License information
        ===================

        Some surfaces have been published under the following
        licenses, please look at the metadata for each surface
        for the specific license:

        """)

        for license in licenses_used:
            license_file_in_archive = f"LICENSE-{license}.txt"
            license_info = settings.CC_LICENSE_INFOS[license]
            readme_txt += textwrap.dedent("""
            {}
            {}
            For details about this license see
            - '{}' (description), or
            - '{}' (legal code), or
            - the included file '{}' (legal code).
            """.format(license_info['title'],
                       "-"*len(license_info['title']),
                       license_info['description_url'],
                       license_info['legal_code_url'],
                       license_file_in_archive))
            #
            # Also add license file
            #
            zf.write(staticfiles_storage.path(f"other/{license}-legalcode.txt"),
                     arcname=license_file_in_archive)

    zf.writestr("README.txt", textwrap.dedent(readme_txt))

    zf.close()
