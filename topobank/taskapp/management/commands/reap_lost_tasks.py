"""
Fail tasks whose worker disappeared.

The same sweep runs on a schedule (see ``topobank.taskapp.custodian``); this
command exists for the cases where waiting two scheduled passes is pointless
because the rows are known to be dead: clearing an old backlog, cleaning up
after an incident, and running as part of a deployment, which restarts every
worker and therefore destroys whatever they were executing.
"""

import time
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError

from ...custodian import (
    DEFAULT_MIN_AGE,
    find_lost,
    live_task_ids,
    mark_lost,
    task_state_models,
)


class Command(BaseCommand):
    help = "Fail tasks stuck in STARTED whose worker no longer exists."

    def add_arguments(self, parser):
        parser.add_argument(
            "--min-age-minutes",
            type=int,
            default=int(DEFAULT_MIN_AGE.total_seconds() // 60),
            help=(
                "Only consider tasks that started at least this long ago "
                "(default: %(default)s). Raise it when clearing an old backlog "
                "to keep recent tasks out of the way."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List what would be failed and change nothing.",
        )
        parser.add_argument(
            "--wait-seconds",
            type=int,
            default=0,
            help=(
                "Keep retrying the broadcast for this long while no worker "
                "answers (default: %(default)s). Needed right after a "
                "deployment, where the workers are still booting and would "
                "otherwise make every running task look lost."
            ),
        )
        parser.add_argument(
            "--allow-no-workers",
            action="store_true",
            help=(
                "Exit successfully instead of failing when no worker answers. "
                "For unattended use, where being unable to check is not a "
                "reason to abort the surrounding process."
            ),
        )

    #: How long to wait between broadcasts while polling for a live worker.
    POLL_INTERVAL = 5

    def _live_task_ids(self, wait_seconds):
        """Task ids known to the fleet, retrying until a worker answers."""
        deadline = time.monotonic() + max(0, wait_seconds)
        while True:
            live = live_task_ids()
            if live is not None:
                return live
            if time.monotonic() >= deadline:
                return None
            self.stdout.write("No worker answered yet, waiting...")
            time.sleep(self.POLL_INTERVAL)

    def handle(self, *args, **options):
        min_age_minutes = options["min_age_minutes"]
        dry_run = options["dry_run"]

        live = self._live_task_ids(options["wait_seconds"])
        if live is None:
            message = (
                "No Celery worker answered the broadcast, so it is impossible to "
                "tell which tasks are still running. Refusing to fail anything. "
                "Check that the workers are up and that the broker is reachable."
            )
            if options["allow_no_workers"]:
                self.stdout.write(self.style.WARNING(f"{message} Skipping."))
                return
            raise CommandError(message)

        self.stdout.write(
            f"{len(live)} task(s) currently known to the workers; "
            f"searching {len(task_state_models())} model(s) for tasks that "
            f"started more than {min_age_minutes} min ago."
        )

        lost = find_lost(live, min_age=timedelta(minutes=min_age_minutes))
        if not lost:
            self.stdout.write(self.style.SUCCESS("No lost tasks found."))
            return

        by_model = {}
        for obj in lost:
            by_model.setdefault(type(obj).__name__, []).append(obj)
        for name, objects in sorted(by_model.items()):
            self.stdout.write(f"  {name}: {len(objects)}")

        if dry_run:
            for obj in lost:
                self.stdout.write(
                    f"  would fail {type(obj).__name__} {obj.pk} (task {obj.task_id})"
                )
            self.stdout.write(
                self.style.WARNING(f"Dry run: {len(lost)} task(s) left untouched.")
            )
            return

        failed = sum(1 for obj in lost if mark_lost(obj))
        self.stdout.write(
            self.style.SUCCESS(
                f"Failed {failed} of {len(lost)} lost task(s). "
                "Any parent waiting on one of them was failed as well."
            )
        )
