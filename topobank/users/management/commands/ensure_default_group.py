from django.core.management.base import BaseCommand

import logging

from topobank.users.models import User, DEFAULT_GROUP_NAME
from topobank.users.utils import get_default_group

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Ensures that a default group exists and all users are member of this group."

    def handle(self, *args, **options):

        _log.info("Ensuring default group '{}' exists..".format(DEFAULT_GROUP_NAME))
        default_group = get_default_group()  # here the group is also created if not existing
        users = User.objects.all()

        _log.info("Ensuring all users are members of this group..")
        for user in users:
            user.groups.add(default_group)

        self.stdout.write(self.style.SUCCESS(
            "Default group '{}' exists and all {} users are members of this group.").format(default_group.name,
                                                                                            users.count()))
        _log.info("Done.")
