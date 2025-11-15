"""
Management command for importing a surface from file(s).

ONLY USE FROM TRUSTED SOURCES!
"""

import datetime
import logging
import zipfile

import yaml
from django.core.management.base import BaseCommand, CommandError
from django.utils.timezone import now

from topobank.manager.models import Surface, Topography
from topobank.properties.models import Property
from topobank.users.models import User

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
            help="Use unsafe YAML loader - use with care, this is potentially dangerous, "
            "malicious code execution is possible.",
        )

        parser.add_argument(
            "--name-as-datafile",
            action="store_true",
            dest="name_as_datafile",
            help='Use the "name" attribute of topographies instead of "datafile". Useful for old container format.',
        )

        parser.add_argument(
            "--ignore-missing",
            action="store_true",
            dest="ignore_missing",
            help="If attributes are missing, try to use feasible defaults . Useful for old container format.",
        )

    def process_topography(
        self, topo_dict, topo_file, surface, ignore_missing=False, dry_run=False
    ):
        self.stdout.write(
            self.style.NOTICE(f"  Topography name: '{topo_dict['name']}'")
        )
        self.stdout.write(
            self.style.NOTICE(f"  Original creator is '{topo_dict['created_by']}'.")
        )

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

        if not dry_run:
            # ...which we need for the storage prefix
            topography.save_datafile(topo_file)
            self.stdout.write(
                self.style.SUCCESS(f"Topography '{topo_name}' saved in database.")
            )
            # Renew/generate cache
            topography.refresh_cache()
        else:
            topography.save()

    def process_dataset_archive(
        self,
        surface_zip,
        user,
        datafile_attribute="datafile",
        ignore_missing=False,
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
        datafile_attribute: str
            attribute in file from which the file name for a topography is stored
        ignore_missing: bool
            If True, try to find reasonable defaults for missing attributes.
        dry_run: bool
            If True, only show what would be done without actually importing data.
        unsafe_yaml_loader: bool
            If True, use an unsafe YAML loader. Use this with care,
            if there is malicious code in the metadata, this can compromise your system.
        """
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
                surface = Surface(
                    created_by=user,
                    name=surface_dict["name"],
                    category=surface_dict["category"],
                    description=surface_description,
                    tags=surface_dict["tags"],
                )
                if not dry_run:
                    surface.save()
                    self.stdout.write(
                        self.style.SUCCESS(f"Surface '{surface.name}' saved.")
                    )

                num_topographies = len(surface_dict["topographies"])
                for topo_idx, topo_dict in enumerate(surface_dict["topographies"]):
                    self.stdout.write(
                        self.style.NOTICE(
                            f"Processing topography {topo_idx + 1}/{num_topographies} in archive..."
                        )
                    )
                    try:
                        datafile_name = topo_dict[datafile_attribute][
                            "original"
                        ]  # there will be more entries later
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
                            f"  Cannot load datafile for '{topo_dict}' from archive. Reason: {exc}"
                        ) from exc
                    try:
                        self.process_topography(
                            topo_dict,
                            topo_file,
                            surface,
                            ignore_missing=ignore_missing,
                            dry_run=dry_run,
                        )
                    except Exception as exc:
                        raise CommandError(
                            f"  Cannot create topography from description {topo_dict}. Reason: {exc}"
                        ) from exc

                if "properties" in surface_dict:
                    num_properties = len(surface_dict["properties"])
                    for prop_idx, prop_dict in enumerate(surface_dict["properties"]):
                        self.stdout.write(
                            self.style.NOTICE(
                                f"Processing property {prop_idx + 1}/{num_properties} in archive..."
                            )
                        )
                        unit = prop_dict.get("unit", None)
                        Property.objects.create(
                            surface=surface,
                            permissions=surface.permissions,
                            name=prop_dict["name"],
                            value_categorical=prop_dict["value"] if unit is None else None,
                            value_numerical=None if unit is None else prop_dict["value"],
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

        datafile_attribute = "name" if options["name_as_datafile"] else "datafile"
        self.stdout.write(
            self.style.NOTICE(
                f"As datafile attribute '{datafile_attribute}' will be used."
            )
        )

        #
        # Then process the given IP archives with surfaces
        #
        for filename in options["surface_archives"]:
            try:
                with zipfile.ZipFile(filename, mode="r") as surface_zip:
                    self.process_dataset_archive(
                        surface_zip,
                        user,
                        datafile_attribute,
                        ignore_missing=options["ignore_missing"],
                        dry_run=options["dry_run"],
                        unsafe_yaml_loader=unsafe_yaml_loader,
                    )
            except Exception as exc:
                err_msg = f"Cannot process file '{filename}'. Reason: {exc}"
                self.stdout.write(self.style.ERROR(err_msg))
                raise CommandError(err_msg) from exc

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING("This was a dry run, nothing has been changed.")
            )
        else:
            self.stdout.write(self.style.SUCCESS("Done."))
