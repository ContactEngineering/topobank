"""Management command for registering all analysis functions in database.

Making the functions available in the database.
"""
from django.core.management.base import BaseCommand
from topobank.analysis.registry import AnalysisRegistry


class Command(BaseCommand):
    help = "Registers all analysis functions in the database."

    def add_arguments(self, parser):
        # Named (optional) arguments
        parser.add_argument(
            '-c',
            '--cleanup',
            action='store_true',
            dest='cleanup',
            help='Delete analysis functions no longer used in code together with their analyses.',
        )

    def handle(self, *args, **options):
        reg = AnalysisRegistry()
        counts = reg.sync_analysis_functions(cleanup=options['cleanup'])

        func_count = counts['funcs_created'] + counts['funcs_updated']
        impl_count = counts['implementations_created'] + counts['implementations_updated']

        self.stdout.write(self.style.SUCCESS("Registered {} analysis functions in total.".format(func_count)))
        self.stdout.write(self.style.SUCCESS("   created: {}".format(counts['funcs_created'])))
        self.stdout.write(self.style.SUCCESS("   updated: {}".format(counts['funcs_updated'])))
        self.stdout.write(self.style.SUCCESS("List of current functions: {}\n".format(
            ', '.join(reg.get_analysis_function_names()))))
        self.stdout.write(self.style.SUCCESS("Registered {} analysis function implementations in total." \
                                             .format(impl_count)))
        self.stdout.write(self.style.SUCCESS("   created: {}".format(counts['implementations_created'])))
        self.stdout.write(self.style.SUCCESS("   updated: {}\n".format(counts['implementations_updated'])))
        self.stdout.write(self.style.SUCCESS("Deleted {} analysis function implementations (because no code found)." \
                                             .format(counts['implementations_deleted'])))
        self.stdout.write(self.style.SUCCESS("Deleted {} analysis functions. Cleanup flag set? {}".format(
            counts['funcs_deleted'], options['cleanup'])))
        self.stdout.write(self.style.SUCCESS("Done."))
