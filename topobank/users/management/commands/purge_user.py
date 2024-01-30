import logging
import sys

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from guardian.shortcuts import get_user_perms, remove_perm
from termsandconditions.models import UserTermsAndConditions

from topobank.analysis.models import Analysis
from topobank.manager.models import Surface, Topography
from topobank.users.models import User

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Deletes a user and all associated data (surfaces, topographies, analyses, files, terms, shares). " + \
           "Handle with care."

    def add_arguments(self, parser):
        parser.add_argument('username', type=str)

    def handle(self, *args, **options):

        try:
            user = User.objects.get(username=options['username'])
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                "User '{}' does not exist.".format(options['username'])))
            sys.exit(1)

        surfaces = Surface.objects.filter(creator=user)
        topographies = Topography.objects.filter(surface__in=surfaces)
        analyses = Analysis.objects.filter(topography__in=topographies)
        userterms = UserTermsAndConditions.objects.filter(user=user)

        _log.info("Removing surface related permissions..")
        for s in surfaces:
            permissions = get_user_perms(user, s)
            for p in permissions:
                remove_perm(p, user, s)

        _log.info("Removing analyses related to surfaces created by user '{}'..".format(user.name))
        analyses.delete()

        _log.info("Removing topographies related to surfaces created by user '{}'..".format(user.name))
        topographies.delete()

        _log.info("Removing surfaces created by user '{}'..".format(user.name))
        surfaces.delete()

        _log.info("Removing terms and conditions seen or accepted by user '{}'..".format(user.name))
        userterms.delete()

        #
        # The media path of this user should not be deleted in general
        # because there might be still data files for topographies
        # which have been uploaded to other users' surfaces!
        #
        # If the path is empty, we can delete it.
        # For S3 this would not be needed, but for file backends.
        #
        media_path = user.get_media_path()
        media_dirs, media_files = default_storage.listdir(media_path)
        if (len(media_dirs) == 0) and (len(media_files)):
            _log.info("Deleting empty media path '%s'..", media_path)
            default_storage.delete(user.get_media_path())

        _log.info("Deleting user object..")
        user.delete()

        self.stdout.write(self.style.SUCCESS(
            "Removed user '{}' and everything related.".format(options['username'])))
        _log.info("Done.")
