"""Management command for registering all analysis functions in database.

Making the functions available in the database.
"""
from django.core.management.base import BaseCommand
from topobank.analysis.registry import AnalysisFunctionRegistry


class Command(BaseCommand):
    help = "Registers all analysis functions in the database."

    def handle(self, *args, **options):
        reg = AnalysisFunctionRegistry()
        counts = reg.sync()

        func_count = counts['funcs_created'] + counts['funcs_updated']
        impl_count = counts['implementations_created'] + counts['implementations_updated']

        self.stdout.write(self.style.SUCCESS("Registered {} analysis functions in total.".format(func_count)))
        self.stdout.write(self.style.SUCCESS("   created: {}".format(counts['funcs_created'])))
        self.stdout.write(self.style.SUCCESS("   updated: {}".format(counts['funcs_updated'])))
        self.stdout.write(self.style.SUCCESS("Registered {} analysis function implementations in total.".format(impl_count)))
        self.stdout.write(self.style.SUCCESS("   created: {}".format(counts['implementations_created'])))
        self.stdout.write(self.style.SUCCESS("   updated: {}".format(counts['implementations_updated'])))


