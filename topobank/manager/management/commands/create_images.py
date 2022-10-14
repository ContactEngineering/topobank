from django.core.management.base import BaseCommand
import logging
import pprint

from topobank.manager.models import Topography
from topobank.taskapp.tasks import renew_topography_thumbnail, renew_topography_dzi

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
            '-n',
            '--none-on-error',
            action='store_true',
            dest='none_on_error',
            help='If image creation fails, store None instead of raising an exception.',
        )

        parser.add_argument(
            '-m',
            '--missing',
            action='store_true',
            dest='missing',
            help='Trigger creation for missing images only. '
                 'Default is to recreate all images regardless whether they exist or not, which may take a long time.',
        )

        parser.add_argument(
            '--no-dzi',
            action='store_true',
            dest='no_dzi',
            help='If given, leave out creation of DZI files.',
        )

        parser.add_argument(
            '--no-thumbnails',
            action='store_true',
            dest='no_thumbnails',
            help='If given, leave out creation of thumbnails.',
        )

        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Just traverse users and show what would be done.',
        )

    def handle(self, *args, **options):
        thumbnail_stats = dict(
            missing=0,
            failed=0,
            created=0,
            total=0,
            background=0,
        )
        dzi_stats = thumbnail_stats.copy()

        for topo in Topography.objects.all():
            size_str = f"{topo.size_x} {topo.unit}"
            if topo.size_y:
                size_str += f" x {topo.size_y} {topo.unit}"

            _log.info(f"Creating images for '{topo.name}', id {topo.id}, size {size_str}..")
            thumbnail_available = topo.has_thumbnail
            dzi_available = topo.has_dzi
            should_have_dzi = topo.size_y is not None

            thumbnail_stats['total'] += 1
            if not thumbnail_available:
                thumbnail_stats['missing'] += 1
            if should_have_dzi:
                dzi_stats['total'] += 1
                if not dzi_available:
                    dzi_stats['missing'] += 1

            if not options['dry_run']:
                if not options['no_thumbnails'] and not (options['missing'] and thumbnail_available):
                    _log.debug(f"Creating thumbnail for '{topo.name}', id {topo.id}..")
                    try:
                        if options['background']:
                            renew_topography_thumbnail.delay(topo.id)
                            thumbnail_stats['background'] += 1
                        else:
                            topo.renew_thumbnail(none_on_error=options['none_on_error'])
                            thumbnail_stats['created'] += 1
                    except Exception as exc:
                        _log.warning(f"Cannot create thumbnail for topography {topo.id}, reason: {exc}")
                        thumbnail_stats['failed'] += 1

                if not options['no_dzi'] and should_have_dzi and not (options['missing'] and dzi_available):
                    _log.debug(f"Creating DZI for '{topo.name}', id {topo.id}..")
                    try:
                        if options['background']:
                            renew_topography_dzi.delay(topo.id)
                            dzi_stats['background'] += 1
                        else:
                            topo.renew_dzi(none_on_error=options['none_on_error'])
                            dzi_stats['created'] += 1
                    except Exception as exc:
                        _log.warning(f"Cannot create DZI for topography {topo.id}, reason: {exc}")
                        dzi_stats['failed'] += 1

        if not options['no_thumbnails']:
            self.stdout.write(
                self.style.SUCCESS(f"Statistics for thumbnails: \n{pprint.pformat(thumbnail_stats)}"))

        if not options['no_dzi']:
            self.stdout.write(
                self.style.SUCCESS(f"Statistics for DZI: \n{pprint.pformat(dzi_stats)}"))

        if options['dry_run']:
            self.stdout.write(self.style.WARNING("This was a dry run, nothing has been changed."))
        else:
            self.stdout.write(self.style.SUCCESS("Done."))
