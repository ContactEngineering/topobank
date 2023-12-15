import logging
from collections import defaultdict

from django.core.management.base import BaseCommand
from guardian.shortcuts import assign_perm

from topobank.manager.models import Surface

from topobank_publication.utils import set_publication_permissions

_log = logging.getLogger(__name__)

ALL_PERMISSIONS = ['view_surface', 'change_surface', 'delete_surface', 'share_surface', 'publish_surface']


class Command(BaseCommand):
    help = """Fix permissions of items.

    Ensures that all users have a defined set of permissions on the items
    created by them. For surfaces the users should be able to
    view, change, delete, share, and publish. Maybe more in future.

    This tool can be used to update the permissions if new default permissions
    were introduced.
    """

    def add_arguments(self, parser):

        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Just traverse users and show what would be done.',
        )

    def handle(self, *args, **options):
        # Fix object permissions
        fixed_published_surfaces = set()
        fixed_unpublished_surfaces = set()
        num_fixed_permissions_for_unpublished = defaultdict(lambda : 0)

        for surface in Surface.objects.all():
            creator = surface.creator
            print(surface, creator, creator.get_all_permissions())
            if surface.is_published:
                if any(creator.has_perm(p, surface) for p in ALL_PERMISSIONS):
                    if not options['dry_run']:
                        # there should be no individual rights for published surfaces
                        set_publication_permissions(surface)
                    fixed_published_surfaces.add(surface)
            else:
                for perm in ALL_PERMISSIONS:
                    print(perm, creator.has_perm(perm, surface))
                    if not creator.has_perm(perm, surface):
                        if not options['dry_run']:
                            assign_perm(perm, surface.creator, surface)
                        num_fixed_permissions_for_unpublished[perm] += 1
                        fixed_unpublished_surfaces.add(surface)

        self.stdout.write(self.style.SUCCESS(
            f"Number of unpublished surfaces changed: {len(fixed_unpublished_surfaces)}"))
        self.stdout.write(self.style.SUCCESS(
            f"Number of published surfaces changed: {len(fixed_published_surfaces)}"))
        self.stdout.write(self.style.SUCCESS("Number of permissions fixed for unpublished surfaces:"))
        for perm in ALL_PERMISSIONS:
            self.stdout.write(self.style.SUCCESS(f"  {perm}: {num_fixed_permissions_for_unpublished[perm]}"))

        if options['dry_run']:
            self.stdout.write(self.style.WARNING("This was a dry run, nothing has been changed."))
        else:
            self.stdout.write(self.style.SUCCESS("Done."))
