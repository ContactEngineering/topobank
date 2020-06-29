from django.core.management.base import BaseCommand
import logging

from topobank.manager.models import Topography
from SurfaceTopography.IO import detect_format, CannotDetectFileFormat

_log = logging.getLogger(__name__)

class Command(BaseCommand):
    help = """Set datafile format for topographies which haven't one yet.

    If the datafile format is set, a file can be loaded more efficiently.
    Normally this is set when uploading a new topography. For some
    old topographies or in case the format specifiers change, it may
    be needed to rerun format detection over all topographies saved in the
    database. This can be done with this command.
    """

    def add_arguments(self, parser):

        parser.add_argument(
            '-a',
            '--all',
            action='store_true',
            dest='all',
            help='Process all topographies, also those which already have a format.',
        )

        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Just traverse topographies but actually do not save format into database.',
        )

    def handle(self, *args, **options):

        format_counts = { None: 0 }
        num_cannot_openend = 0  # number of files which cannot be openend

        topographies = Topography.objects.all()
        if not options['all']:
            topographies = topographies.filter(datafile_format__isnull=True)
        num_topographies = topographies.count()

        for topo in topographies:
            if topo.datafile_format is None:
                try:
                    datafile = topo.datafile
                    # Workaround such that module "SurfaceTopography" recognizes this a binary stream
                    if not hasattr(datafile, 'mode'):
                        datafile.mode = 'rb'
                    datafile_format = detect_format(datafile)
                except CannotDetectFileFormat as exc:
                    msg = f"Could not detect format for topography id {topo.id}: "+str(exc)
                    self.stdout.write(self.style.WARNING(msg))
                    format_counts[None] += 1
                    continue
                except Exception as exc:
                    msg = f"Could not open file for topography id {topo.id}: " + str(exc)
                    self.stdout.write(self.style.WARNING(msg))
                    num_cannot_openend += 1
                    continue

                if not options['dry_run']:
                    topo.datafile_format = datafile_format
                    topo.save()

                if datafile_format not in format_counts:
                    format_counts[datafile_format] = 1
                else:
                    format_counts[datafile_format] += 1

        self.stdout.write(self.style.SUCCESS(f"Processed {num_topographies} specified topographies."))

        if num_cannot_openend == 0:
            self.stdout.write(self.style.SUCCESS("All specified topography files can be opened."))
        else:
            self.stdout.write(self.style.ERROR("In total {} of {} topographies currently cannot be opened.".format(
                num_cannot_openend, num_topographies)))

        self.stdout.write(self.style.SUCCESS("Frequencies of topographies which could be opened:"))
        for fmt, freq in format_counts.items():
            self.stdout.write(self.style.SUCCESS(f"  {fmt}: {freq}"))

        if format_counts[None] == 0:
            self.stdout.write(self.style.SUCCESS("All {} topography files which can be opened can also be loaded.".format(
                num_topographies-num_cannot_openend)))
        else:
            self.stdout.write(self.style.WARNING("In total {} topographies currently can be opened, but not be loaded.".format(
                format_counts[None])))

        if options['dry_run']:
            self.stdout.write(self.style.WARNING("This was a dry run, nothing has been changed."))
