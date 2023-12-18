from django.core.management.base import BaseCommand
from django.contrib.sites.models import Site  # we use this as object which is always there, this is a workaround
from django.conf.urls.static import static
from django.shortcuts import reverse

from notifications.signals import notify

import sys
import logging

from topobank.users.models import User

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

        if options['recipient'] is None:
            recipients = User.objects.all()
        else:
            recipients = User.objects.filter(username=options['recipient'])

            if recipients.count() == 0:
                self.stdout.write(self.style.ERROR(
                    "No users with username '{}' exist.".format(options['recipient'])))
                sys.exit(1)

        message = options['message']

        # notify.send() needs some database instance as "actor", so we get one, but it's pretty arbitrary here
        # This is a workaround, is there a solution more elegant? E.g. specify a user which is admin?
        actor = Site.objects.first()

        if options['changelog']:
            href = static('other/CHANGELOG.md')
        else:
            href = '#'

        notify.send(sender=actor, recipient=recipients, verb="notifies all about", description=message, href=href)
        # See javascript code in template "base.html" for details how the notification is displayed.

        self.stdout.write(self.style.SUCCESS(
            f"Send notification to {recipients.count()} recipients."))
        _log.info("Done.")
