"""
Management command for importing a surface from file(s).

ONLY USE FROM TRUSTED SOURCES!
"""
from django.core.management.base import BaseCommand, CommandError
from django.core.files import File
from django.core.files.storage import default_storage
from django.utils.timezone import now

import zipfile
import sys
import yaml
import logging
import os.path
import datetime

from topobank.manager.models import Surface, Topography
from topobank.users.models import User

_log = logging.getLogger(__name__)

ALL_PERMISSIONS = ['view_surface', 'change_surface', 'delete_surface', 'share_surface', 'publish_surface']


class Command(BaseCommand):
    help = """Import a surface.

    In the web app, users can download surfaces as a ZIP archive.
    For development it's useful to transfer surface data from
    the production system to a development system.
    This command allows to import surface archives which were
    previously downloaded.

    ONLY FOR USE WITH FILES FROM TRUSTED SOURCES.
    """

    def add_arguments(self, parser):

        parser.add_argument(
            'username',
            type=str,
            help='Internal name of an existing user which will be creator of the surface(s).'
        )

        parser.add_argument(
            'surface_archives',
            nargs='+',
            type=str,
            help='filename of surface archive(s)'
        )

        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Just read input files and show what would be done.',
        )

    def process_topography(self, topo_dict, topo_file, surface, dry_run=False):
        self.stdout.write(self.style.NOTICE(f"Processing topography '{topo_dict['name']}'.."))
        self.stdout.write(self.style.NOTICE(f"  Original creator is '{topo_dict['creator']}'."))

        topo_name = topo_dict['name']

        size_x, *size_rest = topo_dict['size']
        size_y = None if len(size_rest) == 0 else size_rest[0]

        user = surface.creator

        topo_kwargs = dict(
            creator=user,
            name=topo_name,
            surface=surface,
            size_x=size_x,
            size_y=size_y,
            height_scale=topo_dict['height_scale'],
            measurement_date=topo_dict['measurement_date'],
            description=topo_dict['description'],
            data_source=topo_dict['data_source'],
            unit=topo_dict['unit'],
            tags=topo_dict['tags'],
            detrend_mode=topo_dict['detrend_mode'],
        )

        # saving topo file in backend
        new_topo_file_path = os.path.join(user.get_media_path(), os.path.basename(topo_name))
        self.stdout.write(self.style.NOTICE(f"  Path got topography file in backend: {new_topo_file_path}"))

        if not dry_run:
            topo_kwargs['datafile'] = default_storage.save(new_topo_file_path, File(topo_file))

        topography = Topography(**topo_kwargs)

        if not dry_run:
            topography.save()
            self.stdout.write(self.style.SUCCESS(f"Topography '{topo_name}' saved in database."))
            topography.renew_thumbnail()

    def process_surface_archive(self, surface_zip, user, dry_run=False):
        """Process surface archive i.e. importing the surfaces.

        Parameters
        ----------
        surface_zip: zipfile.Zipfile
            archive with surfaces
        user: topobank.users.User
            User which should be creator of the surface and all data.
        dry_run: bool
            Ih True, only show what would be done without actually importing data.
        """
        with surface_zip.open('meta.yml', mode='r') as meta_file:
            meta = yaml.load(meta_file)
            # This is potentially unsafe, but needed for the current download format

            for surface_dict in meta['surfaces']:
                import_time = str(now())

                surface_description = surface_dict['description']
                surface_description += f'\n\nImported from file "{surface_zip.filename}" on {import_time}.'
                surface = Surface(creator=user,
                                  name=surface_dict['name'],
                                  category=surface_dict['category'],
                                  description=surface_description,
                                  tags=surface_dict['tags'])
                if not dry_run:
                    surface.save()
                    self.stdout.write(self.style.SUCCESS(f"Surface '{surface.name}' saved."))
                for topo_dict in surface_dict['topographies']:
                    try:
                        topo_file = surface_zip.open(topo_dict['datafile'], mode='r')
                        self.process_topography(topo_dict, topo_file, surface, dry_run=dry_run)
                    except Exception as exc:
                        raise CommandError(f"Cannot create topography from description {topo_dict}. Reason: {exc}")
                if not dry_run:
                    surface.renew_analyses()

    def handle(self, *args, **options):
        """

        Parameters
        ----------
        args
        options

        Returns
        -------
        list of ids of newly created surfaces
        """

        #
        # First try to find given user
        #
        try:
            username = options['username']
            user = User.objects.get(username=username)
            self.stdout.write(self.style.NOTICE(f"User with given username '{username}' found."))
        except User.DoesNotExist:
            err_msg = f"Cannot find user with given username '{username}'."
            self.stdout.write(self.style.ERROR(err_msg))
            raise CommandError(err_msg)

        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run. Nothing will be changed."))

        #
        # Then process the given IP archives with surfaces
        #
        for filename in options['surface_archives']:
            try:
                with zipfile.ZipFile(filename, mode='r') as surface_zip:
                    self.process_surface_archive(surface_zip, user,
                                                 options['dry_run'])
            except Exception as exc:
                err_msg = f"Cannot process file '{filename}'. Reason: {exc}"
                self.stdout.write(self.style.ERROR(err_msg))
                raise CommandError(err_msg) from exc

        if options['dry_run']:
            self.stdout.write(self.style.WARNING("This was a dry run, nothing has been changed."))
        else:
            self.stdout.write(self.style.SUCCESS("Done."))
