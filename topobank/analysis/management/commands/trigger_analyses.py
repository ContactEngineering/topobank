from django.core.management.base import BaseCommand
from guardian.shortcuts import get_users_with_perms
import logging
import sys

from topobank.manager.models import Topography, Surface
from topobank.analysis.models import Analysis
from topobank.analysis.models import AnalysisFunction
from topobank.analysis.utils import submit_analysis, renew_analysis

_log = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Trigger analyses for given surfaces, topographies or functions."

    def add_arguments(self, parser):

        parser.add_argument('item', nargs='+', type=str,
                            help="""
                            Item for which analyses should be triggered.
                            Format:
                              's<surface_id>':    all analyses for a specific surface,
                              't<topography_id>': all analyses for a specific topography,
                              'f<function_id>':   all analyses for a given function,
                              'a<analysis_id>':   a specific analysis,
                              'failed':           all failed analyses,
                              'pending':          all pending analyses.
                            """)

        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Just parse arguments and print how much analyses would be triggered.',
        )

        parser.add_argument(
            '-d',
            '--default-kwargs',
            action='store_true',
            dest='default_kwargs',
            help="""Always use default arguments instead of existing function arguments.
            New analysis (not already existing) will be started with default arguments.
            """,
        )

        parser.add_argument(
            '-l',
            '--list-funcs',
            action='store_true',
            dest='list_funcs',
            help='Just list analysis functions with ids and exit.',
        )

    def parse_item(self, item, analysis_funcs):
        """Parse one item and return set of (function, topography).

        :param item: str with an item from command line
        :param analysis_funcs: sequence of analysis functions to search analyses for
        :return: set of tuple (function, topography)

        The parameter item can be

         "failed": return set for all failed analyses
         "pending": return set for all pending analyses
         "s<surface_id>": return set for all topographies for given surface, e.g. "s13" means surface_id=13
         "t<topo_id>": return set for given topography
         "a<analysis_id>": return set only for given analysis
         "f<analysis_id>": return set for given analysis function and all topographies
        """

        if item == "failed":
            failed_analyses = Analysis.objects.filter(task_state=Analysis.FAILURE, function__in=analysis_funcs)
            self.stdout.write(self.style.SUCCESS(f"Found {len(failed_analyses)} failed analyses."))
            return set( (a.function, a.topography) for a in failed_analyses)

        if item == "pending":
            pending_analyses = Analysis.objects.filter(task_state=Analysis.PENDING, function__in=analysis_funcs)
            self.stdout.write(self.style.SUCCESS(f"Found {len(pending_analyses)} pending analyses."))
            return set( (a.function, a.topography) for a in pending_analyses)

        if item[0] not in 'staf':
            self.stdout.write(self.style.WARNING(f"Cannot interpret first character of item '{item}'. Skipping."))
            return ()

        try:
            id = int(item[1:])
        except ValueError:
            self.stdout.write(self.style.WARNING(f"Cannot interpret id of item '{item}'. Skipping."))
            return ()

        classes = {
            's': Surface,
            't': Topography,
            'a': Analysis,
            'f': AnalysisFunction,
        }

        klass = classes[item[0]]

        try:
            obj = klass.objects.get(id=id)
        except klass.DoesNotExist:
            self.stdout.write(self.style.WARNING(f"Cannot find item '{item}' in database. Skipping."))
            return ()

        result = set()

        if klass == Surface:
            for topo in obj.topography_set.all():
                for af in analysis_funcs:
                    result.add((af, topo))
        elif klass == Topography:
            for af in analysis_funcs:
                result.add((af, obj))
        elif klass == Analysis:
            result.add((obj.function, obj.topography))
        elif klass == AnalysisFunction:
            for topo in  Topography.objects.all():
                result.add((obj, topo))

        return result

    def handle(self, *args, **options):
        #
        # collect analyses to trigger
        #
        auto_analysis_funcs = AnalysisFunction.objects.filter(automatic=True)

        if options['list_funcs']:
            for af in auto_analysis_funcs:
               self.stdout.write(self.style.SUCCESS(f"Id {af.id}: {af.name} (python: {af.pyfunc}, automatic: {af.automatic})"))
            sys.exit(0)

        dry_run = options['dry_run']

        num_triggered = 0

        trigger_set = set()
        for item in options['item']:
            trigger_set.update(self.parse_item(item, auto_analysis_funcs))

        #
        # Trigger analyses
        #
        for func, topo in trigger_set:
            # collect users which are allowed to view analyses
            users = set(get_users_with_perms(topo.surface))
            matching_analyses = Analysis.objects.filter(topography=topo, function=func)

            #
            # Check whether analyses exist which match .. if exist, regenerate with same
            # arguments.
            for a in matching_analyses:
                if not dry_run:
                    a = renew_analysis(a, use_default_kwargs=options['default_kwargs'])
                users.difference_update(set(a.users.all()))  # for some users we have already submitted an analysis
                num_triggered += 1

            # submit with standard arguments for rest of users with view permission
            # which do not have this kind of analysis yet
            if len(users) > 0:
                if not dry_run:
                    submit_analysis(users, func, topo)
                num_triggered += 1

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"Would trigger {num_triggered} analyses, but this is a dry run."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Triggered {num_triggered} analyses."))
