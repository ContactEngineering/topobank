"""
Management command for completing DOIs.

Each publication should have a DOI. Since the creation of DOIs
hasn't be implemented from the beginning, we need this command
to generate missing DOIs.
"""
from django.core.management.base import BaseCommand
from django.conf import settings
import logging

from topobank.publication.models import Publication

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = """Make sure that all publication have a DOI.

    All publications without a DOI are traversed. For each of those publication
    we'll try to generate a DOI, based on the current system settings and
    based on the database entry for this publication.

    The default is a dry-run, then we just traverse all publications
    and show what would be done, but do not really create DOIs or change the database.

    You need to give a special switch to get DOIs created.
    """

    def add_arguments(self, parser):

        parser.add_argument(
            '--do-it',
            action='store_true',
            dest='do_it',
            help='Really create the DOIs. The default is a dry run.',
        )

        parser.add_argument(
            '--force-draft',
            action='store_true',
            dest='force_draft',
            help='Force draft state for new DOIs, independent from application settings. Draft DOIs can '
                 'be deleted, so this can be used for testing.',
        )

    def handle(self, *args, **options):

        #
        # Show DOI settings
        #
        self.stdout.write(self.style.SUCCESS('Settings related to DOI generation:'))
        for settings_name in ['PUBLICATION_URL_PREFIX', 'PUBLICATION_DOI_PREFIX',
                  'DATACITE_USERNAME', 'DATACITE_API_URL', 'PUBLICATION_DOI_STATE']:
            self.stdout.write(self.style.SUCCESS(f'{settings_name}: {getattr(settings, settings_name)}'))

        if options['force_draft']:
            self.stdout.write(self.style.WARNING(f'Doi state will be draft due to given switch!'))

        #
        # Traverse publications
        #
        num_failed = 0
        num_success = 0
        num_with = 0
        num_without = 0

        num_total = Publication.objects.count()

        for pub_idx, pub in enumerate(Publication.objects.order_by('datetime')):
            if pub.doi_name == '':
                num_without += 1
            else:
                num_with += 1
                _log.info(f"Publication '{pub.doi_name}' already has a DOI, skipping.")
                continue

            _log.info(f"Registering DOI for '{pub.short_url}', id {pub.id}, {pub_idx+1}/{num_total}..")
            if options['do_it']:
                try:
                    pub.create_doi(force_draft=options['force_draft'])
                    num_success += 1
                except Exception as exc:
                    _log.warning(f"Could not create DOI for publication '{pub.short_url}', reason: {exc}")
                    num_failed += 1

        self.stdout.write(self.style.SUCCESS(
            f"Statistics before run: #with DOI: {num_with}, #without DOI: {num_without}"))
        self.stdout.write(self.style.SUCCESS(
            f"Statistics after run: #ok: {num_success}, #failed: {num_failed}, #skipped: {num_without}"))

        if options['do_it']:
            self.stdout.write(self.style.SUCCESS("Done."))
        else:
            self.stdout.write(self.style.WARNING("This was a dry run, nothing has been changed. "
                                                 "See help if you really want to create the DOIs."))
