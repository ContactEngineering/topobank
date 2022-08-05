import traceback

from django.core.management.base import BaseCommand
import logging

from topobank.manager.models import Topography
from topobank.taskapp.tasks import renew_bandwidth_cache

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = """Renew bandwidth cache for topographies.

    For each topography, the bandwidth and a short reliabililty cutoff
    is stored in the database. In case the way of calculation has changed
    or some values are missing, this command can be used to recalculate
    these values.
    """

    def add_arguments(self, parser):

        parser.add_argument(
            '--with-traceback',
            action='store_true',
            dest='with_traceback',
            help="On failures, also print traceback so it's easier to localize the problem.",
        )

        parser.add_argument(
            '-b',
            '--background',
            action='store_true',
            dest='background',
            help='Trigger datafile creation in background (task queue), return fast but no statistics about success.',
        )

    def handle(self, *args, **options):
        num_failed = 0
        num_success = 0

        num_total = Topography.objects.count()

        for topo_idx, topo in enumerate(Topography.objects.order_by('name')):
            _log.info(f"Renewing bandwidth cache file for '{topo.name}', id {topo.id}, {topo_idx+1}/{num_total}..")

            try:
                if options['background']:
                    renew_bandwidth_cache.delay(topo.id)
                else:
                    topo.renew_bandwidth_cache()
                num_success += 1
            except Exception as exc:
                _log.error(f"Cannot renew bandwidth cache for topography {topo.id}, reason: {exc}")
                if options['with_traceback']:
                    _log.error(traceback.format_exc())
                num_failed += 1

        self.stdout.write(self.style.SUCCESS(
            f"Statistics after run: #ok: {num_success}, #failed: {num_failed}"))
        if options['background']:
            self.stdout.write(self.style.NOTICE("Recreation has been triggered in the background - "
                                                "success not known yet."))

        if num_failed > 0 and not options['with_traceback']:
            self.stdout.write(self.style.NOTICE("There have been failures. Use option --with-traceback to see details."))

        self.stdout.write(self.style.SUCCESS("Done."))
