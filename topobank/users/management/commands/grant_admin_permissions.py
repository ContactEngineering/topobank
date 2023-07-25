import sys
import logging

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
# from guardian.shortcuts import get_user_perms, remove_perm

from request_profiler.models import ProfilingRecord, RuleSet

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
    ProfilingRecord: ['add', 'view', 'change', 'delete'],
    RuleSet: ['add', 'view', 'change', 'delete'],
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
        # Ensure user has "staff" flag but not the "superuser" flag
        #
        user.is_staff = True
        user.is_superuser = False
        user.save()
        _log.info("User is `staff` member now, but not `superuser`.")

        #
        # Ensure user has permissions needed
        #
        for model, perms in PERMISSIONS_TO_GRANT.items():
            ct = ContentType.objects.get_for_model(model)
            for perm in perms:
                module_name, model_name = ct.natural_key()
                _log.info(f"Obtaining permission object for '{perm}_{model_name}'...")
                perm = Permission.objects.get(codename=f"{perm}_{model_name}", content_type=ct)
                _log.info(f"Granting permission {perm}...")
                user.user_permissions.add(perm)

        self.stdout.write(self.style.SUCCESS(
            "User '{}' should be able to use admin now without being superuser.".format(options['username'])))
        self.stdout.write(self.style.SUCCESS(
            "The corresponding link is available in the user's menu entry."))
        _log.info("Done.")
