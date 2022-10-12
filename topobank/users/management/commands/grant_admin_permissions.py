from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
# from guardian.shortcuts import get_user_perms, remove_perm

import sys
import logging

from topobank.organizations.models import Organization
from topobank.users.models import User

# from topobank.manager.models import Surface, Topography
from topobank.analysis.models import Analysis

_log = logging.getLogger(__name__)

PERMISSIONS_TO_GRANT = {  # key: model, value: list of actions - subset of {"delete", "add", "view", "change"}
    Analysis: ['view', 'change', 'delete'],
    User: ['view'],
    Group: ['add', 'view', 'change', 'delete'],
    Organization: ['add', 'view', 'change', 'delete'],
}


class Command(BaseCommand):
    help = "Ensures that the given user can use the admin interface without granting superuser rights."

    def add_arguments(self, parser):
        parser.add_argument('username', type=str)

    def handle(self, *args, **options):

        try:
            user = User.objects.get(username=options['username'])
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                "User '{}' does not exist.".format(options['username'])))
            sys.exit(1)

        #
        # Ensure user has "staff" flag
        #
        user.is_staff = True
        user.save()
        _log.info("User is staff member now.")

        #
        # Ensure user has permissions needed
        #
        for model, perms in PERMISSIONS_TO_GRANT.items():
            ct = ContentType.objects.get_for_model(model)
            for perm in perms:
                perm = Permission.objects.get(codename=f"{perm}_{ct.name}", content_type=ct)
                _log.info(f"Granting permission {perm}..")
                user.user_permissions.add(perm)

        self.stdout.write(self.style.SUCCESS(
            "User '{}' should be able to use admin now without being superuser.".format(options['username'])))
        self.stdout.write(self.style.SUCCESS(
            "The corresponding link is available in the user's menu entry."))
        _log.info("Done.")
