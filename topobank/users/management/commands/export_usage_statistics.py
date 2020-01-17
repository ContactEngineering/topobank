from django.core.management.base import BaseCommand
from trackstats.models import Metric, StatisticByDate

import pandas as pd
import logging

EXPORT_FILE_NAME = 'usage_statistics.xlsx'

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Exports a file with usage statistics."

    def handle(self, *args, **options):

        metric = Metric.objects.get(ref='login_count')
        logins_by_date = StatisticByDate.objects.filter(metric=metric)

        dates = []
        num_logins = []
        for l in logins_by_date.values():
            dates.append(l['date'])
            num_logins.append(l['value'])


        df = pd.DataFrame({'date': dates, 'num_logins': num_logins})

        df.to_excel(EXPORT_FILE_NAME, sheet_name='number of logins')

        self.stdout.write(self.style.SUCCESS(f"Written user statistics to file '{EXPORT_FILE_NAME}'."))
        _log.info("Done.")
