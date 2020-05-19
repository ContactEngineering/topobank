from django.core.management.base import BaseCommand
import pickle
from collections import defaultdict
import logging

from topobank.analysis.models import Analysis, AnalysisFunction

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = """Save default function kwargs. Process all analyses, inspect function kwargs whether default kwargs
    are missing. Save function kwargs with default arguments added.
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
        # Find out default function kwargs
        #
        default_kwargs = {}
        for af in AnalysisFunction.objects.all():

            try:
                dkw = af.get_default_kwargs()
            except AttributeError as err:
                self.stdout.write(self.style.WARNING(f"Cannot use function '{af.pyfunc}'. Skipping it."))
                continue

            self.stdout.write(self.style.SUCCESS(f"Default arguments for {af.name}: {dkw}"))
            default_kwargs[af] = dkw

        #
        # Process all analyses and compare. Save additional arguments when neeeded.
        #
        for a in Analysis.objects.all():
            analysis_kwargs = pickle.loads(a.kwargs)
            changed = False
            if a.function in default_kwargs:
                for k,v in default_kwargs[a.function].items():
                    if k not in analysis_kwargs:
                        analysis_kwargs[k] = v
                        changed = True
                        num_changed_arguments[k] += 1
            else:
                self.stdout.write(self.style.WARNING(f"Skipping analysis {a.id} because we have no default "+\
                                                         f"arguments for function '{a.function}'."))

            if changed:
                if not options['dry_run']:
                    a.kwargs = pickle.dumps(analysis_kwargs)
                    a.save()
                num_changed_analyses_by_function[a.function] += 1

        num_changed_analyses = sum(num_changed_analyses_by_function.values())

        msg = f"Fixed kwargs of {num_changed_analyses} analyses, "+\
              "now all analyses have kwargs with explicit keyword arguments."
        self.stdout.write(self.style.SUCCESS(msg))

        self.stdout.write(self.style.SUCCESS("Count per analysis function:"))
        for func, func_count in num_changed_analyses_by_function.items():
            self.stdout.write(self.style.SUCCESS(f"  function '{func}': {func_count}"))

        self.stdout.write(self.style.SUCCESS("Count per argument name:"))
        for arg, arg_count in num_changed_arguments.items():
            self.stdout.write(self.style.SUCCESS(f"  argument '{arg}': {arg_count}"))

        if options['dry_run']:
            self.stdout.write(self.style.WARNING("This was a dry-run, nothing was changed in database."))

