"""
Import and export surfaces through archives aka "surface containers".
"""
import zipfile
import os.path
import yaml
import textwrap

from django.utils.timezone import now
from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage

from .models import Topography


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

            topofile_name = os.path.basename(topo_dict['datafile'])
            #
            # Make the filename unique in the archive
            #
            if topofile_name in already_used_topofile_names:
                topofile_name_root, topofile_name_ext = os.path.splitext(topofile_name)
                topofile_name = f"{topofile_name_root}_{counter}.{topofile_name_ext}"
                counter += 1

            topo_dict['datafile'] = topofile_name  # should be same as in archive
            already_used_topofile_names.append(topofile_name)

            # add topography file to ZIP archive
            zf.writestr(topofile_name, topography.datafile.read())

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
