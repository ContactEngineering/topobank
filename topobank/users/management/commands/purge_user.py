from django.core.management.base import BaseCommand
import sys

from topobank.users.models import User
from topobank.manager.models import Surface, Topography
from topobank.analysis.models import Analysis
from termsandconditions.models import UserTermsAndConditions

class Command(BaseCommand):
    help = "Deletes a user and all associated data (surfaces, topographies, files, terms). Handle with care."

    def add_arguments(self, parser):
        parser.add_argument('username', type=str)

    def handle(self, *args, **options):

        try:
            user = User.objects.get(username=options['username'])
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                "User '{}' does not exist.".format(options['username'])))
            sys.exit(1)

        surfaces = Surface.objects.filter(user=user)
        topographies = Topography.objects.filter(surface__in=surfaces)
        analyses = Analysis.objects.filter(topography__in=topographies)
        userterms = UserTermsAndConditions.objects.filter(user=user)

        analyses.delete()
        topographies.delete()
        surfaces.delete()
        userterms.delete()
        user.delete()

        self.stdout.write(self.style.SUCCESS(
            "Removed user '{}' and everything related.".format(options['username'])))

