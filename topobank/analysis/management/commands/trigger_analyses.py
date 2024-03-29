import logging
import sys

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from topobank.analysis.controller import renew_analyses_for_subject, renew_existing_analysis, submit_analysis
from topobank.analysis.models import Analysis, AnalysisFunction
from topobank.manager.models import Surface, Topography

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

        parser.add_argument(
            '-r',
            '--related',
            action='store_true',
            dest='related',
            help='If given for surfaces, the analyses of the related topographies will also be triggered.',
        )

        parser.add_argument(
            '-d',
            '--default-kwargs',
            action='store_true',
            dest='use_default_kwargs',
            help='Use default kwargs of the corresponding analysis function instead of the keyword arguments'
                 ' saved for this analysis in the database.',
        )

    def parse_item(self, item, use_default_kwargs=False, related=False):
        """Parse one item and trigger analyses.

        Parameters
        ----------

            item: str
                Item from command line, see help text.
            use_default_kwargs: bool
                If True, use default keyword arguments from analysis function instead of those from the analysis,
                but only for "analysis" items, not for "subject" items starting with 's', 't', 'f' + number.

        Returns
        -------
        list of TriggerCommand instances


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
                renew_existing_analysis(a, use_default_kwargs=use_default_kwargs)
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
                    self.style.SUCCESS(f"Renewed analyses for {ct.name} '{obj}'.")
                )
                if related and ct.name == 'surface':
                    for topo in obj.topography_set.all():
                        renew_analyses_for_subject(topo)
                        self.stdout.write(
                            self.style.SUCCESS(f"Renewed analyses for topography '{obj}'.")
                        )
            elif ct.name == "analysis":
                renew_existing_analysis(obj, use_default_kwargs=use_default_kwargs)
                self.stdout.write(
                    self.style.SUCCESS(f"Renewed analysis '{obj}'.")
                )
            elif ct.name == "analysis function":
                num_analyses = 0
                for ct_impl_type in obj.get_implementation_types():
                    subjects = ct_impl_type.get_all_objects_for_this_type()
                    for subject in subjects:
                        users_for_subject = subject.get_users_with_perms()
                        # filter users whether allowed to use implementation
                        users = [u for u in users_for_subject if
                                 obj.get_implementation(ct_impl_type).is_available_for_user(u)]
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
            self.parse_item(item, use_default_kwargs=options['use_default_kwargs'], related=options['related'])
