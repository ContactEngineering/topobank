from django.core.management.base import BaseCommand

from topobank.analysis.functions import register_all

class Command(BaseCommand):
    help = "Registers all analysis functions in the database."

    def handle(self, *args, **options):
        num_funcs = register_all()

        self.stdout.write(self.style.SUCCESS("Registered {} analysis functions.".format(num_funcs)))


