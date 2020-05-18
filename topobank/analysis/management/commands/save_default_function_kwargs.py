from django.core.management.base import BaseCommand
import inspect
import pickle
import logging

from topobank.analysis.models import Analysis, AnalysisFunction

_log = logging.getLogger(__name__)


def get_default_args(func):
    # thanks to mgilson, his answer on SO:
    # https://stackoverflow.com/questions/12627118/get-a-function-arguments-default-value#12627202
    signature = inspect.signature(func)
    return {
        k: v.default
        for k, v in signature.parameters.items()
        if v.default is not inspect.Parameter.empty
    }

class Command(BaseCommand):
    help = """Save default function kwargs. Process all analyses, inspect function kwargs whether default kwargs
    are missing. Save function kwargs with default arguments added.
    """

    # def add_arguments(self, parser):
    #
    #     # Named (optional) arguments
    #     parser.add_argument(
    #         '-a',
    #         '--all',
    #         action='store_true',
    #         dest='all',
    #         help='Delete all analyses including all result files.',
    #     )

    def handle(self, *args, **options):

        dry_run = True

        num_changed_analyses = 0

        #
        # Find out default function kwargs
        #
        default_kwargs = {}
        for af in AnalysisFunction.objects.all():
            dkw = get_default_args(af.python_function)

            if 'storage_prefix' in dkw:
                del dkw['storage_prefix']
            if 'progress_recorder' in dkw:
                del dkw['progress_recorder']

            self.stdout.write(self.style.SUCCESS(f"Default arguments for {af.name}: {dkw}"))
            default_kwargs[af] = dkw

        #
        # Process all analyses and compare. Save additional arguments when neeeded.
        #
        for a in Analysis.objects.all():
            analysis_kwargs = pickle.loads(a.kwargs)
            changed = False
            for k,v in default_kwargs[a.function].items():
                if k not in analysis_kwargs:
                    analysis_kwargs[k] = v
                    changed = True

            if changed:
                if not dry_run:
                    a.kwargs = pickle.dumps(analysis_kwargs)
                    a.save()
                num_changed_analyses += 1


        msg = f"Fixed kwargs of {num_changed_analyses} analyses, "+\
              "now all analyses have kwargs with explicit keyword arguments."
        self.stdout.write(self.style.SUCCESS(msg))
        if dry_run:
            self.stdout.write(self.style.WARNING("This was a dry-run nothing was changed."))

