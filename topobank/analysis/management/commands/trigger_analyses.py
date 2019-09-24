from django.core.management.base import BaseCommand
from guardian.shortcuts import get_users_with_perms
import logging

from topobank.manager.models import Topography, Surface
from topobank.analysis.models import Analysis
from topobank.analysis.models import AnalysisFunction
from topobank.analysis.utils import submit_analysis

_log = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Trigger analyses. So for analyses for all functions will be triggered."

    def add_arguments(self, parser):

        parser.add_argument('items', nargs='+', type=str,
                            help="Items for which analyses should be triggered. Format: "+\
                            "'s<surfarce_id>' for surfaces and 't<topography_id>' for topographies. "+\
                            "Use 'failed' for all failed analyses.")


        # Named (optional) arguments
        #parser.add_argument(
        #    '-a',
        #    '--all',
        #    action='store_true',
        #    dest='all',
        #    help='Delete all analyses including all result files.',
        #)

    def parse_item(self, item, analysis_funcs):
        """Parse one item and return set of (function, topography).

        :param item: str with an item from command line
        :param analysis_funcs: sequence of analysis functions to search analyses for
        :return: set of tuple (function, topography)

        The parameter item can be

         "failed": return set for all failed analyses
         "s<surface_id>": return set for all topographies for given surface, e.g. "s13" means surface_id=13
         "t<topo_id>: return set for given topography
        """

        if item == "failed":
            failed_analyses = Analysis.objects.filter(task_state=Analysis.FAILURE, function__in=analysis_funcs)
            self.stdout.write(self.style.SUCCESS(f"Found {len(failed_analyses)} failed analyses."))
            return set( (a.function, a.topography) for a in failed_analyses)


        if item[0] not in ['s', 't']:
            self.stdout.write(self.style.WARNING(f"Cannot interpret first character of item '{item}'. Skipping."))
            return ()

        try:
            id = int(item[1:])
        except ValueError:
            self.stdout.write(self.style.WARNING(f"Cannot interpret id of item '{item}'. Skipping."))
            return ()

        is_surface = item[0] == 's'

        if is_surface:
            klass = Surface
        else:
            klass = Topography

        try:
            obj = klass.objects.get(id=id)
        except klass.DoesNotExist:
            self.stdout.write(self.style.WARNING(f"Cannot find item '{item}' in database. Skipping."))
            return ()

        result = set()

        if is_surface:
            for topo in obj.topography_set.all():
                for af in analysis_funcs:
                    result.add((af, topo))
        else:
            for af in analysis_funcs:
                result.add((af, obj))

        return result

    def handle(self, *args, **options):
        #
        # collect topographies and surfaces
        #
        auto_analysis_funcs = AnalysisFunction.objects.filter(automatic=True)

        num_triggered = 0

        trigger_set = set()
        for item in options['items']:
            trigger_set.update(self.parse_item(item, auto_analysis_funcs) )

        #
        # Trigger analyses
        #
        for func, topo in trigger_set:
            # collect users which are allowed to view analyses
            users = get_users_with_perms(topo.surface)
            submit_analysis(users, func, topo)
            num_triggered += 1

        self.stdout.write(self.style.SUCCESS(f"Triggered {num_triggered} analyses."))
