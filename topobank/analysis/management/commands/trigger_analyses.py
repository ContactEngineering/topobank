from django.core.management.base import BaseCommand
from django.contrib.contenttypes.models import ContentType
from guardian.shortcuts import get_users_with_perms
import logging
import sys
from abc import ABC, abstractmethod

from topobank.manager.models import Topography, Surface
from topobank.analysis.models import Analysis
from topobank.analysis.models import AnalysisFunction
from topobank.analysis.utils import submit_analysis, renew_analysis, renew_analyses_for_subject

_log = logging.getLogger(__name__)

CONTENTTYPES = {c: ContentType.objects.get_for_model(klass)
                for c, klass in zip('staf', [Surface, Topography, Analysis, AnalysisFunction])}


class Command(BaseCommand):
    help = "Trigger analyses for given surfaces, topographies or functions."

    def add_arguments(self, parser):

        parser.add_argument('item', nargs='*', type=str,
                            help="""
                            Item for which analyses should be triggered.
                            Format:
                              's<surface_id>':    all analyses for a specific surface,
                              't<topography_id>': all analyses for a specific topography,
                              'a<analysis_id>':   a specific, existing analysis,
                              'f<function_id>':   analyses for a given function and all subjects,
                              'failed':           all failed analyses,
                              'pending':          all pending analyses.
                            """)

        parser.add_argument(
            '-l',
            '--list-funcs',
            action='store_true',
            dest='list_funcs',
            help='Just list analysis functions with ids and exit.',
        )

    def parse_item(self, item):
        """Parse one item and trigger analyses.

        :param item: str with an item from command line
        :return: list of TriggerCommand instances

        The parameter item can be

         "failed": return set for all failed analyses
         "pending": return set for all pending analyses
         "s<surface_id>": return set for all related analyses for given surface, e.g. "s13" means surface_id=13
         "t<topo_id>": return set for given topography
         "a<analysis_id>": return set only for given analysis
         "f<function_id>": return set for given analysis function and all subjects
        """

        if item in ["failed", "pending"]:
            task_state = item[:2]
            analyses = Analysis.objects.filter(task_state=task_state)
            for a in analyses:
                renew_analysis(a)
            self.stdout.write(
                self.style.SUCCESS(f"Found {len(analyses)} analyses with task state '{task_state}'.")
            )
        elif item[0] not in CONTENTTYPES.keys():
            self.stdout.write(self.style.WARNING(f"Cannot interpret first character of item '{item}'. Skipping."))
        else:
            try:
                obj_id = int(item[1:])
            except ValueError:
                self.stdout.write(self.style.WARNING(f"Cannot interpret id of item '{item}'. Skipping."))
                return

            ct = CONTENTTYPES[item[0]]

            try:
                obj = ct.get_object_for_this_type(id=obj_id)
            except ct.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"Cannot find item '{item}' in database. Skipping."))
                return

            if ct.name in ['surface', 'topography']:
                renew_analyses_for_subject(obj)
                self.stdout.write(
                    self.style.SUCCESS(f"Renewed analyses for subject '{obj}'.")
                )
            elif ct.name == "analysis":
                renew_analysis(obj)
                self.stdout.write(
                    self.style.SUCCESS(f"Renewed analysis '{obj}'.")
                )
            elif ct.name == "analysis function":
                num_analyses = 0
                for ct in obj.get_implementation_types():
                    subjects = ct.get_all_objects_for_this_type()
                    for subject in subjects:
                        related_surface = subject if isinstance(subject, Surface) else subject.surface
                        users = get_users_with_perms(related_surface)
                        submit_analysis(users, obj, subject)
                        self.stdout.write(
                            self.style.SUCCESS(f"Triggered analysis for function '{obj}' and subject '{subject}'.")
                        )
                        num_analyses += 1
                self.stdout.write(
                    self.style.SUCCESS(f"Triggered {num_analyses} analyses for function '{obj}'.")
                )
            else:
                self.stdout.write(self.style.WARNING(f"Don't know how to handle contenttype '{ct.name}'."))


    def handle(self, *args, **options):

        if options['list_funcs']:
            analysis_funcs = AnalysisFunction.objects.all()
            for af in analysis_funcs:
                type_names_str = ", ".join([t.name for t in af.get_implementation_types()])
                self.stdout.write(self.style.SUCCESS(f"f{af.id}: {af.name}, implemented for: {type_names_str}"))
            sys.exit(0)

        for item in options['item']:
            self.parse_item(item)
