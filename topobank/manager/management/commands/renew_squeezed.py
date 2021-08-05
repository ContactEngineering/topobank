from django.core.management.base import BaseCommand
import logging

from topobank.manager.models import Topography
from topobank.taskapp.tasks import renew_squeezed_datafile

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = """Renew squeezed data files for topographies.

    Recreate squeezed data file for all topographies..
    """

    def add_arguments(self, parser):

        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Just traverse users and show what would be done.',
        )

        parser.add_argument(
            '-b',
            '--background',
            action='store_true',
            dest='background',
            help='Trigger datafile creation in background (task queue), return fast but no statistics about success.',
        )

        parser.add_argument(
            '-m',
            '--missing',
            action='store_true',
            dest='missing',
            help='Only recreate missing squeezed data files.',
        )

    def handle(self, *args, **options):

        num_failed = 0
        num_success = 0
        num_skipped = 0
        num_with = 0
        num_without = 0

        num_total = Topography.objects.count()

        for topo_idx, topo in enumerate(Topography.objects.order_by('name')):
            if not topo.has_squeezed_datafile:
                num_without += 1
            else:
                num_with += 1

            if topo.has_squeezed_datafile and options['missing']:
                num_skipped += 1
                continue

            _log.info(f"Renewing squeezed data file for '{topo.name}', id {topo.id}, {topo_idx+1}/{num_total}..")
            if not options['dry_run']:
                try:
                    if options['background']:
                        renew_squeezed_datafile.delay(topo.id)
                    else:
                        topo.renew_squeezed_datafile()
                    num_success += 1
                except Exception as exc:
                    _log.warning(f"Cannot recreate squeezed data file for topography {topo.id}, reason: {exc}")
                    num_failed += 1

        self.stdout.write(self.style.SUCCESS(
            f"Statistics before run: #with: {num_with}, #without: {num_without}"))
        self.stdout.write(self.style.SUCCESS(
            f"Statistics after run: #ok: {num_success}, #failed: {num_failed}, #skipped: {num_skipped}"))
        if options['background']:
            self.stdout.write(self.style.NOTICE("Recreation has been triggered in the background - "
                                                "success not known yet."))

        if options['dry_run']:
            self.stdout.write(self.style.WARNING("This was a dry run, nothing has been changed."))
        else:
            self.stdout.write(self.style.SUCCESS("Done."))
