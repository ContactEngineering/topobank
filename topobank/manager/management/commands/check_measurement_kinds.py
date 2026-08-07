import logging

from django.core.management.base import BaseCommand

from topobank.manager.models import Measurement
from topobank.measurements.channels import ChannelError
from topobank.measurements.registry import sniff_measurement_file

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = """Check that every measurement's kind matches its data file.

    The migration that introduced `Measurement.kind` derived it from columns that
    were already in the database rather than by re-reading every data file, which
    would have meant one object-storage read per measurement. That inference is
    reliable for measurements that had been inspected, but it is an inference.

    This command opens each data file and compares the kind its selected channel
    implies against the stored one. It reports and does not write, so it is safe to
    run at any time; `refresh_cache` is the command that repairs what this finds.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Check at most this many measurements.",
        )
        parser.add_argument(
            "--kind",
            default=None,
            help="Only check measurements of this kind.",
        )

    def handle(self, *args, **options):
        measurements = Measurement.objects.exclude(kind="").order_by("id")
        if options["kind"]:
            measurements = measurements.filter(kind=options["kind"])
        if options["limit"]:
            measurements = measurements[: options["limit"]]

        checked = 0
        mismatched = []
        unreadable = []

        for measurement in measurements.iterator(chunk_size=100):
            checked += 1
            try:
                inspection = sniff_measurement_file(measurement)
                index = inspection.resolve(
                    measurement.channel_name, measurement.channel_occurrence
                )
                actual = inspection.channels[index].kind
            except ChannelError as exc:
                unreadable.append((measurement.id, f"channel: {exc}"))
                continue
            except Exception as exc:
                unreadable.append((measurement.id, str(exc)))
                continue

            if actual != measurement.kind:
                mismatched.append((measurement.id, measurement.kind, actual))

        self.stdout.write(f"Checked {checked} measurement(s).")

        if mismatched:
            self.stdout.write(
                self.style.ERROR(
                    f"{len(mismatched)} measurement(s) have a kind that does not "
                    "match their data file. Run `refresh_cache` for these to "
                    "correct them:"
                )
            )
            for pk, stored, actual in mismatched:
                self.stdout.write(f"  measurement {pk}: stored {stored!r}, file says {actual!r}")
        else:
            self.stdout.write(
                self.style.SUCCESS("All checked measurements match their data file.")
            )

        if unreadable:
            # Not necessarily a problem with the kind: the file may be missing or
            # the recorded channel may have gone away.
            self.stdout.write(
                self.style.WARNING(
                    f"{len(unreadable)} measurement(s) could not be checked:"
                )
            )
            for pk, reason in unreadable:
                self.stdout.write(f"  measurement {pk}: {reason}")
