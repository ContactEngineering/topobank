import logging

from django.core.management.base import BaseCommand

from topobank.analysis.models import WorkflowResult

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Deletes analyses from the database."

    def add_arguments(self, parser):

        # Named (optional) arguments
        parser.add_argument(
            '-a',
            '--all',
            action='store_true',
            dest='all',
            help='Delete all analyses including all result files.',
        )

    def handle(self, *args, **options):

        if options['all']:
            _log.info("Deleting all analyses because of management command.")
            num_deleted, _ = WorkflowResult.objects.all().delete()

            self.stdout.write(self.style.SUCCESS("Deleted {} analyses from database.".format(num_deleted)))
        else:
            self.stdout.write(
                self.style.WARNING("Nothing deleted. Can only delete all analyses up to now. See help (-h)."))
