from django.core.management.base import BaseCommand
import logging
from guardian.shortcuts import get_users_with_perms

from topobank.analysis.models import Analysis

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Set default users for analyses. "

    # def add_arguments(self, parser):
    #
    #     # Named (optional) arguments
    #     parser.add_argument(
    #         '-a',
    #         '--all',
    #         action='store_true',
    #         dest='all',
    #         help='Delete all analyses including all result files.',
    #     )

    def handle(self, *args, **options):

        num_dangling_analyses = 0

        for a in Analysis.objects.all():
            #
            # If this analysis has no users attached to, assign creator and all
            # users the related surface is shared with
            #
            if a.users.count() == 0:
                num_dangling_analyses += 1
                analysis_users = list(set(get_users_with_perms(s) for s in a.related_surfaces()))

                _log.info("Setting users for analysis '{}': {}".format(a, analysis_users))

                a.users.add(*analysis_users)

        msg = "Fixed {} dangling analyses, now all analyses have users attached.".format(num_dangling_analyses)
        self.stdout.write(self.style.SUCCESS(msg))

        #
        # TODO Check that each users is only attached to one combination of topography, function and arguments
        #


