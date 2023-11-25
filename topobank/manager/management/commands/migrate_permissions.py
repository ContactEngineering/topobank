import logging

from guardian.shortcuts import UserObjectPermission, GroupObjectPermission
from django.core.management.base import BaseCommand
from topobank.manager.models import Surface, SurfaceUserObjectPermission, SurfaceGroupObjectPermission
from django.db import transaction


_log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Migrates permissons from generic 'UserObjectPermission' to direct 'SurfaceUserObjectPermission'"

    def handle(self, *args, **options):
        # Migrating User permissions
        user_object_perms = UserObjectPermission.objects.all()  # 'old' user perms
        _log.info(f"Migrating {user_object_perms.count()} UserObjectPermissions")
        if SurfaceUserObjectPermission.objects.all().count() == 0:
            _log.info(f"Migrating {user_object_perms.count()} permissions...")
            with transaction.atomic():
                for user_object_perm in user_object_perms:
                    SurfaceUserObjectPermission.objects.create(user=user_object_perm.user,
                                                               content_object=user_object_perm.content_object,
                                                               permission=user_object_perm.permission)
            _log.info("Successfully migrated UserObjectPermission!")
        else:
            _log.info(f"There exist already {SurfaceUserObjectPermission.objects.all().count()} 'SurfaceUserObjectPermission' Objects, skipping migration")
        # Migrating group permissions
        group_object_perms = GroupObjectPermission.objects.all()  # 'old' group perms
        _log.info(f"Migrating {group_object_perms.count()} GroupObjectPermissions")
        if SurfaceGroupObjectPermission.objects.all().count() == 0:
            _log.info(f"Migrating {group_object_perms.count()} permissions...")
            with transaction.atomic():
                for group_object_perm in group_object_perms:
                    SurfaceGroupObjectPermission.objects.create(group=group_object_perm.group,
                                                                content_object=group_object_perm.content_object,
                                                                permission=group_object_perm.permission)
            _log.info("Successfully migrated GroupObjectPermission!")
        else:
            _log.info(f"There exist already {SurfaceUserObjectPermission.objects.all().count()} 'SurfaceUserObjectPermission' Objects, skipping migration")
