import logging
from collections import defaultdict

from django.core.management.base import BaseCommand

from topobank.analysis.models import Analysis, Workflow
from topobank.analysis.registry import WorkflowNotImplementedException

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = """Save default function kwargs. Process all analyses, inspect function kwargs whether default kwargs
    are missing. Save function kwargs with default arguments added.

    This command assumes that all analysis function have been registered before.
    If not call 'register_analysis_functions' before. Maybe you want to clean up
    old analyses, which have no more implementation.
    """

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
        # Find out default implementation function kwargs, create lookup table
        # in order to reduce database requests
        #
        default_kwargs = {}  # key: analysis function implementation
        for af in Workflow.objects.all():
            for impl in af.implementations.all():
                try:
                    dkw = impl.default_kwargs
                except AttributeError:
                    self.stdout.write(self.style.WARNING(f"Cannot use implementation '{impl}'. Skipping it."))
                    continue

                self.stdout.write(self.style.SUCCESS(
                    f"Default arguments for function {af.name}, {impl.subject_type}: {dkw}"))
                default_kwargs[impl] = dkw

        #
        # Process all analyses and compare kwargs with default kwargs of corresponding
        # implementations. Save additional default arguments in analysis instance if
        # they are missing. So we can assure that all analysis have all values for all parameters.
        #
        for a in Analysis.objects.all():
            analysis_kwargs = a.kwargs
            try:
                impl = a.function.get_implementation(a.subject_type)
            except WorkflowNotImplementedException:
                self.stdout.write(self.style.WARNING(f"Skipping analysis {a.id} because the implementation "
                                                     "no longer exists and we cannot determine default parameters."))
                continue

            changed = False
            if impl in default_kwargs:
                for k, v in default_kwargs[impl].items():
                    if k not in analysis_kwargs:
                        analysis_kwargs[k] = v
                        changed = True
                        num_changed_arguments[k] += 1
            else:
                self.stdout.write(self.style.WARNING(f"Skipping analysis {a.id} because we have no default "
                                                     f"arguments for function '{a.function}' and subject "
                                                     f"typ {a.subject_type}."))

            if changed:
                if not options['dry_run']:
                    a.kwargs = analysis_kwargs
                    a.save()
                num_changed_analyses_by_function[a.function] += 1

        num_changed_analyses = sum(num_changed_analyses_by_function.values())

        msg = f"Fixed kwargs of {num_changed_analyses} analyses, " + \
              "now all analyses have kwargs with explicit keyword arguments."
        self.stdout.write(self.style.SUCCESS(msg))

        if num_changed_analyses_by_function:
            self.stdout.write(self.style.SUCCESS("Count per analysis function:"))
            for func, func_count in num_changed_analyses_by_function.items():
                self.stdout.write(self.style.SUCCESS(f"  function '{func}': {func_count}"))

        if num_changed_arguments:
            self.stdout.write(self.style.SUCCESS("Count per argument name:"))
            for arg, arg_count in num_changed_arguments.items():
                self.stdout.write(self.style.SUCCESS(f"  argument '{arg}': {arg_count}"))

        if options['dry_run']:
            self.stdout.write(self.style.WARNING("This was a dry-run, nothing was changed in database."))
