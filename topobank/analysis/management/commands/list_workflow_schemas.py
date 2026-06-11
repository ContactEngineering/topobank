import json

from django.core.management.base import BaseCommand, CommandError

from topobank.analysis.models import Workflow
from topobank.analysis.registry import get_workflow_names


class Command(BaseCommand):
    help = """List registered workflows together with the JSON schema and the
    default values of their keyword arguments (parameters)."""

    def add_arguments(self, parser):
        parser.add_argument(
            "--name",
            help="Only show the workflow with this registry name.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Emit a machine-readable JSON document on stdout instead of "
            "formatted text. Warnings go to stderr so the output can be piped.",
        )
        parser.add_argument(
            "--indent",
            type=int,
            default=2,
            help="Indentation level for JSON output. (Default: 2)",
        )
        parser.add_argument(
            "--output",
            help="Write JSON to this file instead of stdout (implies --json). "
            "Use this when log handlers write to stdout and would corrupt "
            "piped output.",
        )

    def handle(self, *args, **options):
        names = sorted(get_workflow_names())
        if options["name"]:
            if options["name"] not in names:
                raise CommandError(
                    f"Workflow '{options['name']}' is not registered. "
                    f"Registered workflows: {', '.join(names)}"
                )
            names = [options["name"]]

        entries = []
        for name in names:
            workflow = Workflow(name=name)
            entry = {"name": name, "display_name": workflow.display_name}
            try:
                entry["kwargs_schema"] = workflow.get_kwargs_schema()
                entry["default_kwargs"] = workflow.get_default_kwargs()
            except Exception as e:
                entry["error"] = str(e)
                self.stderr.write(
                    self.style.WARNING(f"Cannot get schema for '{name}': {e}")
                )
            entries.append(entry)

        if options["output"]:
            with open(options["output"], "w") as f:
                json.dump(entries, f, indent=options["indent"])
                f.write("\n")
            self.stderr.write(
                self.style.SUCCESS(
                    f"Wrote {len(entries)} workflow schemas to {options['output']}"
                )
            )
            return

        if options["as_json"]:
            self.stdout.write(json.dumps(entries, indent=options["indent"]))
            return

        for entry in entries:
            self.stdout.write(
                self.style.MIGRATE_HEADING(
                    f"{entry['name']} ({entry['display_name']})"
                )
            )
            if "error" in entry:
                self.stdout.write(self.style.WARNING(f"  error: {entry['error']}"))
                continue
            self.stdout.write(self.style.SUCCESS("  Default kwargs:"))
            self.stdout.write(
                "    " + json.dumps(entry["default_kwargs"], default=str)
            )
            self.stdout.write(self.style.SUCCESS("  Kwargs schema:"))
            for line in json.dumps(
                entry["kwargs_schema"], indent=options["indent"]
            ).splitlines():
                self.stdout.write("    " + line)
            self.stdout.write("")
