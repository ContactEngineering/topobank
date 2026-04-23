import logging
from collections import defaultdict

from django.core.management.base import BaseCommand

from topobank.analysis.models import Workflow, WorkflowResult
from topobank.analysis.registry import (
    WorkflowNotImplementedException,
    get_analysis_function_names,
)

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = """Save default function kwargs. Process all analyses, inspect function kwargs whether default kwargs
    are missing. Save function kwargs with default arguments added."""

    def add_arguments(self, parser):
        # Named (optional) arguments
        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Print how much function arguments would be changed without actually doing it.',
        )

    def handle(self, *args, **options):

        num_changed_analyses_by_function = defaultdict(int)
        num_changed_arguments = defaultdict(int)

        #
        # Build lookup table of default kwargs per workflow name
        #
        default_kwargs = {}  # key: workflow name
        for name in get_analysis_function_names():
            workflow = Workflow(name=name)
            try:
                dkw = workflow.get_default_kwargs()
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Cannot get default kwargs for '{name}': {e}. Skipping."))
                continue
            self.stdout.write(self.style.SUCCESS(f"Default arguments for workflow {name}: {dkw}"))
            default_kwargs[name] = dkw

        #
        # Process all analyses and compare kwargs with default kwargs.
        #
        for a in WorkflowResult.objects.all():
            analysis_kwargs = a.kwargs
            workflow_name = a.workflow_name
            if workflow_name is None:
                continue

            try:
                Workflow(name=workflow_name).get_default_kwargs()
            except WorkflowNotImplementedException:
                self.stdout.write(self.style.WARNING(
                    f"Skipping analysis {a.id} because the implementation "
                    "no longer exists and we cannot determine default parameters."
                ))
                continue

            changed = False
            if workflow_name in default_kwargs:
                for k, v in default_kwargs[workflow_name].items():
                    if k not in analysis_kwargs:
                        analysis_kwargs[k] = v
                        changed = True
                        num_changed_arguments[k] += 1
            else:
                self.stdout.write(self.style.WARNING(
                    f"Skipping analysis {a.id} because we have no default "
                    f"arguments for workflow '{workflow_name}'."
                ))

            if changed:
                if not options['dry_run']:
                    a.kwargs = analysis_kwargs
                    a.save()
                num_changed_analyses_by_function[workflow_name] += 1

        num_changed_analyses = sum(num_changed_analyses_by_function.values())

        msg = f"Fixed kwargs of {num_changed_analyses} analyses, " + \
              "now all analyses have kwargs with explicit keyword arguments."
        self.stdout.write(self.style.SUCCESS(msg))

        if num_changed_analyses_by_function:
            self.stdout.write(self.style.SUCCESS("Count per analysis function:"))
            for func, func_count in num_changed_analyses_by_function.items():
                self.stdout.write(self.style.SUCCESS(f"  workflow '{func}': {func_count}"))

        if num_changed_arguments:
            self.stdout.write(self.style.SUCCESS("Count per argument name:"))
            for arg, arg_count in num_changed_arguments.items():
                self.stdout.write(self.style.SUCCESS(f"  argument '{arg}': {arg_count}"))

        if options['dry_run']:
            self.stdout.write(self.style.WARNING("This was a dry-run, nothing was changed in database."))
