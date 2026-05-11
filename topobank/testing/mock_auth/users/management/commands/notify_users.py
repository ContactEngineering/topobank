import logging

from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand
from notifications.signals import notify

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    """Command for sending notifications to users."""
    help = """Send a notification to all or a bunch of users.

    The recipients can read the notification when logged in.
    """

    def add_arguments(self, parser):

        parser.add_argument('message', type=str,
                            help="Message to be sent to the user.")
        parser.add_argument(
            '-r',
            '--recipient',
            type=str,
            default=None,
            dest='recipient',
            help='Username of the user who is the recipient. If not given, send to all users.',
        )
        parser.add_argument(
            '--changelog',
            action='store_true',
            dest='changelog',
            help='Clicking the notification links to the current Changelog file. Default is a link to home.',
        )

    def handle(self, *args, **options):
        User = get_user_model()

        if options['recipient'] is None:
            recipients = User.objects.all()
        else:
            recipients = User.objects.filter(username=options['recipient'])

            if recipients.count() == 0:
                self.stdout.write(self.style.ERROR(
                    "No users with username '{}' exist.".format(options['recipient'])))
                return

        message = options['message']

        actor = Site.objects.first()
        if actor is None:
            self.stdout.write(self.style.WARNING(
                "No Site objects exist. Cannot send notification."))
            return

        href = '#'

        notify.send(sender=actor, recipient=recipients, verb="notifies all about", description=message, href=href)

        self.stdout.write(self.style.SUCCESS(
            f"Send notification to {recipients.count()} recipients."))
        _log.info("Done.")
