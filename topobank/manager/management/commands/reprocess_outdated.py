from django.core.management.base import BaseCommand

from topobank.manager.reprocessing import configured_steps, outdated_topographies
from topobank.taskapp.utils import run_task


class Command(BaseCommand):
    help = """Process again the measurements whose derived files are out of date.

    Out of date are the derived files of a measurement that a configured
    processing step (TOPOBANK_PROCESSING_STEPS) applies to, but whose files were
    not written by the step's current version and options -- e.g. after a step
    was added to the deployment. Each is dispatched like an upload, through the
    processing backend; measurements whose processing is in flight are skipped.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report how many measurements are out of date.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Dispatch at most this many measurements.",
        )
        parser.add_argument(
            "--retry-failed",
            action="store_true",
            help="Also process measurements whose current step failed.",
        )

    def handle(self, *args, dry_run=False, limit=None, retry_failed=False, **options):
        steps = ", ".join(f"{step.name} {version}" for step, version in configured_steps())
        self.stdout.write(f"Configured processing steps: {steps}")
        queryset = outdated_topographies(retry_failed=retry_failed).order_by("pk")
        total = queryset.count()
        self.stdout.write(f"{total} measurement(s) are out of date.")
        if dry_run:
            return
        if limit is not None:
            queryset = queryset[:limit]
        dispatched = skipped = 0
        for topography in queryset.iterator():
            if run_task(topography):
                dispatched += 1
            else:
                skipped += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Dispatched {dispatched}; skipped {skipped} already in progress."
            )
        )
