from django.core.management.base import BaseCommand
import logging
import math

from topobank.manager.models import Topography
from topobank.manager.utils import get_topography_reader

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    """Fix height scale in database."""
    help = """Fix height_scale_editable of measurements.

    Each measurement/topography has a field 'height_scale_editable'.
    Since version 0.94.0 of SurfaceTopography, the reader channels
    return None if the height scale was not fixed by the file
    contents. It returns a number, when it is fixed by the file
    and should not be changed by the user.

    In Topobank, each Topography in the database has a field
    'height_scale_editable' which controls whether the field
    can be changed in the UI. For new measurements, this is set
    correctly, but there might be old entries with wrong settings.

    This scripts sets the field according to what SurfaceTopography
    returns, so the database is consistent. Might be needed after
    upgrade to SurfaceTopography 0.04.0 or later.

    Also the height_scale itself is fixed in the database, if the
    factor is not editable but differs from the factor given in the channel.
    """

    def add_arguments(self, parser):

        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Just traverse topographies but actually do change database but show what would be done.',
        )

    def handle(self, *args, **options):

        #
        # Counters
        #
        num_cannot_opened = 0  # number of topographies which cannot be opened
        num_saved = 0

        num_different_editable = 0  # number of topographies which have differences in height_scale_editable
        num_different_factor = 0  # number of topographies which have differences in height_scale factor

        num_not_editable = 0
        num_editable = 0
        num_editable_not_1 = 0  # number of topographies with height scales factors given unequal 1

        topographies = Topography.objects.all()
        num_topographies = topographies.count()
        self.stdout.write(self.style.NOTICE(f"Processing {num_topographies} topographies..."))
        for idx, topo in enumerate(topographies):
            do_save = False  # flag which controls whether this topography is saved
            try:
                reader = get_topography_reader(topo.datafile, format=topo.datafile_format)
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"Cannot open reader for topography {topo.id}: {exc}"))
                num_cannot_opened += 1
                continue

            channel = reader.channels[topo.data_source]
            height_scale_editable = channel.height_scale_factor is None

            if height_scale_editable:
                num_editable += 1
                if not math.isclose(topo.height_scale, 1.):
                    num_editable_not_1
            else:
                num_not_editable += 1

            if height_scale_editable != topo.height_scale_editable:
                num_different_editable += 1
                if not options['dry_run']:
                    topo.height_scale_editable = height_scale_editable
                    do_save = True

            if (not height_scale_editable) and math.isclose(channel.height_scale_factor, topo.height_scale):
                num_different_editable += 1
                if not options['dry_run']:
                    topo.height_scale = channel.height_scale_factor
                    do_save = True

            if do_save:
                topo.save()
                num_saved += 1

            if (idx + 1) % 10 == 0:
                self.stdout.write(self.style.NOTICE(f"Processed {idx+1} topographies so far.."))

        self.stdout.write(self.style.SUCCESS(f"Processed {num_topographies} topographies."))
        self.stdout.write(self.style.SUCCESS(f"Number of editable height scale factors: {num_editable}"))
        self.stdout.write(self.style.SUCCESS(f"                 ... of which are not 1: {num_editable_not_1}"))
        self.stdout.write(self.style.SUCCESS(f"Number of fixed height scale factors: {num_not_editable}"))
        self.stdout.write(
            self.style.SUCCESS(f"Number of detected differences in editable flag: {num_different_editable}"))
        self.stdout.write(
            self.style.SUCCESS(f"Number of detected differences in factor: {num_different_factor}"))
        self.stdout.write(self.style.SUCCESS(f"Number of saved measurements: {num_saved}"))

        if options['dry_run']:
            self.stdout.write(self.style.WARNING("This was a dry run, nothing has been changed."))
        self.stdout.write(self.style.NOTICE("Done"))
