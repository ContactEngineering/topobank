import logging

from django.core.management.base import BaseCommand
from SurfaceTopography.IO import CannotDetectFileFormat, detect_format

from topobank.manager.models import Measurement

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = """Set datafile format for measurements which haven't one yet.

    If the datafile format is set, a file can be loaded more efficiently.
    Normally this is set when uploading a new measurement. For some
    old measurements or in case the format specifiers change, it may
    be needed to rerun format detection over all measurements saved in the
    database. This can be done with this command.
    """

    def add_arguments(self, parser):

        parser.add_argument(
            '-a',
            '--all',
            action='store_true',
            dest='all',
            help='Process all measurements, also those which already have a format.',
        )

        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Just traverse measurements but actually do not save format into database.',
        )

    def handle(self, *args, **options):

        format_counts = {None: 0}
        num_cannot_openend = 0  # number of files which cannot be openend

        measurements = Measurement.objects.all()
        if not options['all']:
            measurements = measurements.filter(datafile_format__isnull=True)
        num_measurements = measurements.count()

        for measurement in measurements:
            if measurement.datafile_format is None:
                try:
                    datafile = measurement.datafile
                    # Workaround such that module "SurfaceTopography" recognizes this a binary stream
                    if not hasattr(datafile, 'mode'):
                        datafile.mode = 'rb'
                    datafile_format = detect_format(datafile)
                except CannotDetectFileFormat as exc:
                    msg = f"Could not detect format for measurement id {measurement.id}: " + str(exc)
                    self.stdout.write(self.style.WARNING(msg))
                    format_counts[None] += 1
                    continue
                except Exception as exc:
                    msg = f"Could not open file for measurement id {measurement.id}: " + str(exc)
                    self.stdout.write(self.style.WARNING(msg))
                    num_cannot_openend += 1
                    continue

                if not options['dry_run']:
                    measurement.datafile_format = datafile_format
                    measurement.save()

                if datafile_format not in format_counts:
                    format_counts[datafile_format] = 1
                else:
                    format_counts[datafile_format] += 1

        self.stdout.write(self.style.SUCCESS(f"Processed {num_measurements} specified measurements."))

        if num_cannot_openend == 0:
            self.stdout.write(self.style.SUCCESS("All specified measurement files can be opened."))
        else:
            self.stdout.write(self.style.ERROR("In total {} of {} measurements currently cannot be opened.".format(
                num_cannot_openend, num_measurements)))

        self.stdout.write(self.style.SUCCESS("Frequencies of measurements which could be opened:"))
        for fmt, freq in format_counts.items():
            self.stdout.write(self.style.SUCCESS(f"  {fmt}: {freq}"))

        if format_counts[None] == 0:
            self.stdout.write(
                self.style.SUCCESS("All {} measurement files which can be opened can also be loaded.".format(
                    num_measurements - num_cannot_openend)))
        else:
            self.stdout.write(
                self.style.WARNING("In total {} measurements currently can be opened, but not be loaded.".format(
                    format_counts[None])))

        if options['dry_run']:
            self.stdout.write(self.style.WARNING("This was a dry run, nothing has been changed."))
