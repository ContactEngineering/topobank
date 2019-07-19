from django.core.management.base import BaseCommand
import logging

from topobank.manager.models import Topography, Surface
from topobank.analysis.models import Analysis
from topobank.analysis.models import AnalysisFunction
from topobank.taskapp.tasks import submit_analysis

_log = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Trigger analyses. So for analyses for all functions will be triggered."

    def add_arguments(self, parser):

        parser.add_argument('items', nargs='+', type=str,
                            help="Items for which analyses should be triggered. Format: "+\
                            "'s<surfarce_id>' for surfaces and 't<topography_id>' for topographies.")


        # Named (optional) arguments
        #parser.add_argument(
        #    '-a',
        #    '--all',
        #    action='store_true',
        #    dest='all',
        #    help='Delete all analyses including all result files.',
        #)

    def handle(self, *args, **options):


        #
        # collect topographies and surfaces
        #
        auto_analysis_funcs = AnalysisFunction.objects.filter(automatic=True)

        num_triggered = 0
        surfaces = []
        topographies = []
        topographies_already_triggered = []

        for item in options['items']:

            if item[0] not in ['s', 't']:
                self.stdout.write(self.style.WARNING(f"Cannot interpret first character of item '{item}'. Skipping."))
                continue

            try:
                id = int(item[1:])
            except ValueError:
                self.stdout.write(self.style.WARNING(f"Cannot interpret id of item '{item}'. Skipping."))
                continue

            is_surface = item[0] == 's'

            if is_surface:
                klass = Surface
            else:
                klass = Topography

            try:
                obj = klass.objects.get(id=id)
            except klass.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"Cannot find item '{item}' in database. Skipping."))
                continue

            if is_surface:
                surfaces.append(obj)
            else:
                topographies.append(obj)

        #
        # Trigger analyses
        #
        for surface in surfaces:

            for topo in surface.topography_set.all():
                for af in auto_analysis_funcs:
                    submit_analysis(af, topo)
                    num_triggered += 1
                topographies_already_triggered.append(topo)

        for topo in topographies:
            if topo not in topographies_already_triggered:
                for af in auto_analysis_funcs:
                    submit_analysis(af, topo)
                    num_triggered += 1

        self.stdout.write(self.style.SUCCESS(f"Triggered {num_triggered} analyses."))
