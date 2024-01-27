import logging
import math

from django.core.management.base import BaseCommand

from topobank.manager.models import Topography
from topobank.manager.utils import get_topography_reader

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    """Fix sizes in database."""
    help = """Fix sizes of measurements.

    Each measurement/topography has a field 'sizes_editable'.
    Since version 0.94.0 of SurfaceTopography, the reader channels
    return None if the sizes were not fixed by the file
    contents. It returns a number (1D) or a tuple of numbers (2D),
    when it is fixed by the file and should not be changed by the user.

    In Topobank, each Topography in the database has a field
    'sizes_editable' which controls whether the field
    can be changed in the UI. For new measurements, this is set
    correctly, but there might be old entries with wrong settings.

    This scripts sets the field according to what SurfaceTopography
    returns, so the database is consistent. Might be needed after
    upgrade to SurfaceTopography 0.94.0 or later.

    Also the sizes itself is fixed in the database, if the
    factor is not editable but differs from what is given in the channel.
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
        num_different_sizes = 0  # number of topographies which have differences in sizes

        num_not_editable = 0
        num_editable = 0

        topographies_with_differences = set()

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
            size_editable = channel.physical_sizes is None
            channel_sizes = channel.physical_sizes

            if size_editable:
                num_editable += 1
            else:
                num_not_editable += 1

            if size_editable != topo.size_editable:
                num_different_editable += 1
                topographies_with_differences.add(topo)
                if not options['dry_run']:
                    topo.size_editable = size_editable
                    topo.unit_editable = size_editable
                    do_save = True

            if not size_editable:  # we don't change the sizes if they're editable
                assert isinstance(channel_sizes, tuple)

                has_2_dim = len(channel_sizes) == 2
                sizes_equal = math.isclose(channel_sizes[0], topo.size_x)
                if has_2_dim:
                    sizes_equal = sizes_equal and math.isclose(channel_sizes[1], topo.size_y)

                if not sizes_equal:
                    num_different_sizes += 1
                    topographies_with_differences.add(topo)
                    if not options['dry_run']:
                        topo.size_x = channel_sizes[0]
                        if has_2_dim:
                            topo.size_y = channel_sizes[1]
                        else:
                            topo.size_y = None
                        do_save = True

            if do_save:
                self.stdout.write(self.style.NOTICE(f"Saving topography {topo.id}, name '{topo.name}'.."))
                topo.save()
                num_saved += 1

            if (idx + 1) % 10 == 0:
                self.stdout.write(self.style.NOTICE(f"Processed {idx+1} topographies so far.."))

        self.stdout.write(self.style.SUCCESS(f"Processed {num_topographies} topographies."))
        self.stdout.write(self.style.SUCCESS(f"Number of editable sizes: {num_editable}"))
        self.stdout.write(self.style.SUCCESS(f"Number of sizes fixed by file contents: {num_not_editable}"))
        self.stdout.write(
            self.style.SUCCESS(f"Number of detected differences in editable flag: {num_different_editable}"))
        self.stdout.write(
            self.style.SUCCESS(f"Number of detected differences in sizes: {num_different_sizes}"))
        self.stdout.write(
            self.style.NOTICE(f"Found differences for {len(topographies_with_differences)} these topographies:"))
        for td in topographies_with_differences:
            self.stdout.write(self.style.NOTICE(f"    topography {td.id}, name '{td.name}'"))
        self.stdout.write(self.style.SUCCESS(f"Number of saved measurements: {num_saved}"))

        if options['dry_run']:
            self.stdout.write(self.style.WARNING("This was a dry run, nothing has been changed."))
        self.stdout.write(self.style.NOTICE("Done"))
