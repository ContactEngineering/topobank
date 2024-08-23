import logging
import sys

from django.core.management.base import BaseCommand

from topobank.users.models import User

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Ensures that the given user can use the admin interface without granting superuser rights."

    def add_arguments(self, parser):
        parser.add_argument("username", type=str)

    def handle(self, *args, **options):

        try:
            user = User.objects.get(username=options["username"])
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    "User '{}' does not exist.".format(options["username"])
                )
            )
            sys.exit(1)

        #
        # Ensure user has "staff" flag but not the "superuser" flag
        #
        user.is_staff = True
        user.is_superuser = False
        user.save()
        _log.info("User is `staff` member now, but not `superuser`.")

        self.stdout.write(
            self.style.SUCCESS(
                "User '{}' should be able to use admin now without being superuser.".format(
                    options["username"]
                )
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                "The corresponding link is available in the user's menu entry."
            )
        )
        _log.info("Done.")
