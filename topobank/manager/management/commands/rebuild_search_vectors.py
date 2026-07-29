from django.core.management.base import BaseCommand

from topobank.manager.models import Surface


class Command(BaseCommand):
    help = (
        "Rebuild the full-text search vectors of all datasets. Vectors are "
        "normally kept up to date by signal handlers; use this command to "
        "repair them, e.g. after bulk database operations or user renames."
    )

    def handle(self, *args, **options):
        nb_surfaces = 0
        for surface in Surface.all_objects.all().iterator():
            surface.update_search_vector()
            nb_surfaces += 1
        self.stdout.write(
            self.style.SUCCESS(f"Rebuilt search vectors of {nb_surfaces} datasets.")
        )
