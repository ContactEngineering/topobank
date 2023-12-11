from itertools import product

from django.core.management.base import BaseCommand
import logging

from guardian.shortcuts import get_perms

from topobank.manager.models import Surface, SurfaceUserObjectPermission
from topobank.users.models import User

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = """Compares permissions in 'UserObjectPermission' and in 'SurfaceObjectPermission' after migration 0045 those
    should be equal.
    """

    def handle(self, *args, **options):
        all_perms_match = True
        users = User.objects.all()
        datasets = Surface.objects.all()
        for user, dataset in product(users, datasets):
            SurfaceUserObjectPermission.enabled = False
            perms_old = get_perms(user, dataset)
            SurfaceUserObjectPermission.enabled = True
            perms_new = get_perms(user, dataset)
            if perms_new != perms_old:
                _log.warning(f"Permissions don't match!\nUser: {user}\nDataset: {dataset}\nPermissions_old: {perms_old}"
                             f"\nPermissions_new: {perms_new}")
                all_perms_match = False
        _log.info(f"Permission Integrity check completed: {'not' if not all_perms_match else 'all'} permissions match")
