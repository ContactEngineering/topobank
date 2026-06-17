"""
Management command for importing a surface from file(s).

ONLY USE FROM TRUSTED SOURCES!
"""

import logging
import zipfile

from django.contrib.auth import get_user_model as _get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils.timezone import now

from topobank.manager.import_zip import load_container_metadata
from topobank.manager.models import Surface, Topography
from topobank.properties.models import Property

User = _get_user_model()

_log = logging.getLogger(__name__)


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
            "username",
            type=str,
            help="Internal name of an existing user which will be creator of the surface(s).",
        )

        parser.add_argument(
            "surface_archives",
            nargs="+",
            type=str,
            help="filename of surface archive(s)",
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Just read input files and show what would be done.",
        )

        parser.add_argument(
            "--unsafe-yaml-loader",
            action="store_true",
            dest="unsafe_yaml_loader",
            help="Use unsafe YAML loader when reading a legacy 'meta.yml' - use with care, "
            "this is potentially dangerous, malicious code execution is possible.",
        )

        parser.add_argument(
            "--ignore-missing",
            action="store_true",
            dest="ignore_missing",
            help="Deprecated and ignored: defaults for missing attributes are now "
            "supplied by the container metadata schema.",
        )

    def process_topography(self, topo_meta, topo_file, surface, dry_run=False):
        self.stdout.write(self.style.NOTICE(f"  Topography name: '{topo_meta.name}'"))
        if topo_meta.created_by is not None:
            self.stdout.write(
                self.style.NOTICE(
                    f"  Original creator is '{topo_meta.created_by.name}'."
                )
            )

        topo_name = topo_meta.name

        size_x, *size_rest = topo_meta.size
        size_y = None if len(size_rest) == 0 else size_rest[0]

        user = surface.created_by

        topo_kwargs = dict(
            created_by=user,
            name=topo_name,
            surface=surface,
            size_x=size_x,
            size_y=size_y,
            measurement_date=topo_meta.measurement_date,
            description=topo_meta.description,
            data_source=topo_meta.data_source,
            unit=topo_meta.unit,
            tags=topo_meta.tags,
            fill_undefined_data_mode=topo_meta.fill_undefined_data_mode,
            detrend_mode=topo_meta.detrend_mode,
            is_periodic=topo_meta.is_periodic,
        )

        if topo_meta.instrument is not None:
            topo_kwargs.update(
                instrument_name=topo_meta.instrument.name or "",
                instrument_type=topo_meta.instrument.type or "",
                instrument_parameters=topo_meta.instrument.parameters,
            )

        if topo_meta.height_scale is not None:
            # If height_scale is not included, it has probably already been
            # applied because of the file contents while loading.
            topo_kwargs["height_scale"] = topo_meta.height_scale

        # Constructing the instance validates the metadata. On a dry run we stop
        # here: nothing is persisted (the surface is not saved either, so saving
        # the topography would fail on the unsaved foreign key).
        topography = Topography(**topo_kwargs)

        if not dry_run:
            # ...which we need for the storage prefix
            topography.save_datafile(topo_file)
            self.stdout.write(
                self.style.SUCCESS(f"Topography '{topo_name}' saved in database.")
            )
            # Renew/generate cache
            topography.refresh_cache()

    def process_dataset_archive(
        self,
        surface_zip,
        user,
        dry_run=False,
        unsafe_yaml_loader=False,
    ):
        """Process surface archive i.e. importing the surfaces.

        Parameters
        ----------
        surface_zip: zipfile.Zipfile
            archive with surfaces
        user: topobank.users.User
            User which should be creator of the surface and all data.
        dry_run: bool
            If True, only show what would be done without actually importing data.
        unsafe_yaml_loader: bool
            If True, use an unsafe YAML loader for a legacy 'meta.yml'. Use this with care,
            if there is malicious code in the metadata, this can compromise your system.
        """
        meta = load_container_metadata(
            surface_zip, unsafe_yaml_loader=unsafe_yaml_loader
        )

        for surface_meta in meta.surfaces:
            import_time = str(now())

            surface_description = surface_meta.description
            surface_description += (
                f'\n\nImported from file "{surface_zip.filename}" on {import_time}.'
            )
            surface = Surface(
                created_by=user,
                name=surface_meta.name,
                category=surface_meta.category,
                description=surface_description,
                tags=surface_meta.tags,
            )
            if not dry_run:
                surface.save()
                self.stdout.write(
                    self.style.SUCCESS(f"Surface '{surface.name}' saved.")
                )

            num_topographies = len(surface_meta.topographies)
            for topo_idx, topo_meta in enumerate(surface_meta.topographies):
                self.stdout.write(
                    self.style.NOTICE(
                        f"Processing topography {topo_idx + 1}/{num_topographies} in archive..."
                    )
                )
                datafile_name = topo_meta.datafile.original
                try:
                    self.stdout.write(
                        self.style.NOTICE(
                            f"  Trying to read file '{datafile_name}' in archive..."
                        )
                    )
                    topo_file = surface_zip.open(datafile_name, mode="r")
                    self.stdout.write(
                        self.style.NOTICE(
                            f"  Datafile '{datafile_name}' found in archive."
                        )
                    )
                except Exception as exc:
                    raise CommandError(
                        f"  Cannot load datafile '{datafile_name}' from archive. Reason: {exc}"
                    ) from exc
                try:
                    self.process_topography(
                        topo_meta,
                        topo_file,
                        surface,
                        dry_run=dry_run,
                    )
                except Exception as exc:
                    raise CommandError(
                        f"  Cannot create topography '{topo_meta.name}'. Reason: {exc}"
                    ) from exc

            if surface_meta.properties and not dry_run:
                num_properties = len(surface_meta.properties)
                for prop_idx, prop_meta in enumerate(surface_meta.properties):
                    self.stdout.write(
                        self.style.NOTICE(
                            f"Processing property {prop_idx + 1}/{num_properties} in archive..."
                        )
                    )
                    unit = prop_meta.unit
                    Property.objects.create(
                        surface=surface,
                        permissions=surface.permissions,
                        name=prop_meta.name,
                        value_categorical=prop_meta.value if unit is None else None,
                        value_numerical=None if unit is None else prop_meta.value,
                        unit=unit,
                    )

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
            username = options["username"]
            user = User.objects.get(username=username)
            self.stdout.write(
                self.style.NOTICE(f"User with given username '{username}' found.")
            )
        except User.DoesNotExist:
            err_msg = f"Cannot find user with given username '{username}'."
            self.stdout.write(self.style.ERROR(err_msg))
            raise CommandError(err_msg)

        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run. Nothing will be changed."))
        unsafe_yaml_loader = options["unsafe_yaml_loader"]
        if unsafe_yaml_loader:
            self.stdout.write(
                self.style.WARNING("You are using an unsafe YAML loader.")
            )

        #
        # Then process the given archives with surfaces
        #
        for filename in options["surface_archives"]:
            try:
                with zipfile.ZipFile(filename, mode="r") as surface_zip:
                    self.process_dataset_archive(
                        surface_zip,
                        user,
                        dry_run=dry_run,
                        unsafe_yaml_loader=unsafe_yaml_loader,
                    )
            except Exception as exc:
                err_msg = f"Cannot process file '{filename}'. Reason: {exc}"
                self.stdout.write(self.style.ERROR(err_msg))
                raise CommandError(err_msg) from exc

        if dry_run:
            self.stdout.write(
                self.style.WARNING("This was a dry run, nothing has been changed.")
            )
        else:
            self.stdout.write(self.style.SUCCESS("Done."))
