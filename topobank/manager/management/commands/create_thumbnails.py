from django.core.management.base import BaseCommand
import logging

from topobank.manager.models import Topography

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = """Create thumbnails for topographies.

    Ensures that all topographies have a thumbnail.
    """

    def add_arguments(self, parser):

        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Just traverse users and show what would be done.',
        )

    def handle(self, *args, **options):

        for topo in Topography.objects.all():
            size_str = f"{topo.size_x} {topo.unit}"
            if topo.size_y:
                size_str += f" x {topo.size_y} {topo.unit}"

            _log.info(f"Creating thumbnail for '{topo.name}', id {topo.id}, size {size_str}..")
            if not options['dry_run']:
                topo.renew_thumbnail()

        if options['dry_run']:
            self.stdout.write(self.style.WARNING("This was a dry run, nothing has been changed."))
        else:
            self.stdout.write(self.style.SUCCESS("Done."))
