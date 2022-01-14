from django.core.management.base import BaseCommand
import logging

from topobank.manager.models import Topography
from topobank.manager.utils import get_firefox_webdriver
from topobank.taskapp.tasks import renew_topography_images

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = """Create thumbnails and deep zoom images for topographies.

    Ensures that all topographies have a thumbnail and that 2D maps have deep zoom images.
    """

    def add_arguments(self, parser):

        parser.add_argument(
            '-b',
            '--background',
            action='store_true',
            dest='background',
            help='Trigger creation of images in background (task queue).',
        )

        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Just traverse users and show what would be done.',
        )

    def handle(self, *args, **options):

        driver = get_firefox_webdriver()
        num_failed = 0
        num_okay = 0
        num_background = 0

        for topo in Topography.objects.all():
            size_str = f"{topo.size_x} {topo.unit}"
            if topo.size_y:
                size_str += f" x {topo.size_y} {topo.unit}"

            _log.info(f"Creating images for '{topo.name}', id {topo.id}, size {size_str}..")
            if not options['dry_run']:
                try:
                    if options['background']:
                        renew_topography_images.delay(topo.id)
                        num_background += 1
                    else:
                        topo.renew_images(driver=driver)
                        num_okay += 1
                except Exception as exc:
                    _log.warning(f"Cannot create images for topography {topo.id}, reason: {exc}")
                    num_failed += 1

        self.stdout.write(self.style.SUCCESS(f"Statistics: #ok: {num_okay}, #failed: {num_failed}, "
                                             f"#background: {num_background}"))

        if options['dry_run']:
            self.stdout.write(self.style.WARNING("This was a dry run, nothing has been changed."))
        else:
            self.stdout.write(self.style.SUCCESS("Done."))
