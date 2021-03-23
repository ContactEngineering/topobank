"""
Management command for importing a surface from file(s).

ONLY USE FROM TRUSTED SOURCES!
"""
from django.core.management.base import BaseCommand
from django.core.files import File
from django.core.files.storage import default_storage

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
    This command allows to import a surface archive which was
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
            help='filename(s) of surface archives'
        )

        parser.add_argument(
            '-n',
            '--name',
            type=str,
            dest='surface_name',
            default='Imported Surface',
            help='Name which should be given to the imported surface. Default: "Imported Surface"'
        )

        parser.add_argument(
            '-c',
            '--category',
            type=str,
            choices=[c[0] for c in Surface.CATEGORY_CHOICES],
            dest='category',
            default='exp',
            help='Category of the imported surface. Default: exp'
        )

        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Just read input files and show what would be done.',
        )


    def process_topography(self, topo_descr, topo_file, surface, dry_run=False):
        self.stdout.write(self.style.NOTICE(f"Processing topography '{topo_descr['name']}'.."))
        self.stdout.write(self.style.NOTICE(f"  Original creator is '{topo_descr['creator']}'."))

        topo_name = topo_descr['name']

        size_x, size_y = topo_descr['size']
        user = surface.creator

        topo_kwargs = dict(
            creator=user,
            name=topo_name,
            surface=surface,
            size_x=size_x,
            size_y=size_y,
            height_scale=topo_descr['height_scale'],
            measurement_date=topo_descr['measurement_date'],
            description=topo_descr['description'],
            data_source=topo_descr['data_source'],
            unit=topo_descr['unit'],
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


    def process_surface_archive(self, surface_zip, surface, dry_run=False):
        """Process surface archive i.e. importing the surface.

        Parameters
        ----------
        surface_zip: zipfile.Zipfile
            archive with the surface
        user: topobank.users.User
            User which should be creator of the surface and all data.
        surface_name: str
            name of the new surface
        dry_run: bool
            Ih True, only show what would be done without actually importing data.
        """
        with surface_zip.open('meta.yml', mode='r') as meta_file:
            meta = yaml.load(meta_file)
            # This is potentially unsafe, but needed for the current download format

            for topo_descr in meta:
                topo_file = surface_zip.open(topo_descr['name'], mode='r')
                self.process_topography(topo_descr, topo_file, surface, dry_run=dry_run)


    def handle(self, *args, **options):

        #
        # First try to find given user
        #
        try:
            username = options['username']
            user = User.objects.get(username=username)
            self.stdout.write(self.style.NOTICE(f"User with given username '{username}' found."))
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Cannot find user with given username '{username}'."))
            sys.exit(1)

        self.stdout.write(self.style.NOTICE(f"New surface will have the name '{options['surface_name']}'."))

        dry_run = options['dry_run']
        now = datetime.datetime.now()

        #
        # Then process the given IP archives with surfaces
        #
        for filename in options['surface_archives']:
            try:
                surface_name = options['surface_name']
                surface = Surface(creator=user, name=surface_name,
                                  description=f'Imported from file "{filename}" on {now}.')
                if not dry_run:
                    surface.save()
                    self.stdout.write(self.style.SUCCESS(f"Surface '{surface_name}' saved."))
                with zipfile.ZipFile(filename, mode='r') as surface_zip:
                    self.process_surface_archive(surface_zip, surface,
                                                 options['dry_run'])
                if not dry_run:
                    surface.renew_analyses()
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"Cannot process file '{filename}'. Reason: {exc}"))

        if options['dry_run']:
            self.stdout.write(self.style.WARNING("This was a dry run, nothing has been changed."))
        else:
            self.stdout.write(self.style.SUCCESS("Done."))
