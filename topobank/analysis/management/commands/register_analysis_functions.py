"""Management command for listing all registered analysis functions.

The Workflow database model has been removed. Workflow metadata is now
derived from the implementation registry at runtime; there is nothing to
register. This command is kept for backwards compatibility and now just
lists the currently registered functions.
"""
from django.core.management.base import BaseCommand

from topobank.analysis.registry import get_analysis_function_names


class Command(BaseCommand):
    help = "Lists all registered analysis functions (no-op since Workflow DB model was removed)."

    def handle(self, *args, **options):
        names = sorted(get_analysis_function_names())
        self.stdout.write(self.style.SUCCESS(
            f"Found {len(names)} registered analysis functions:"
        ))
        for name in names:
            self.stdout.write(f"  {name}")
        self.stdout.write(self.style.SUCCESS("Done."))
