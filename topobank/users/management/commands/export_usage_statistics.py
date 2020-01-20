from django.core.management.base import BaseCommand
from django.contrib.contenttypes.models import ContentType

from trackstats.models import Metric, StatisticByDate, StatisticByDateAndObject

import pandas as pd
import logging

EXPORT_FILE_NAME = 'usage_statistics.xlsx'

_log = logging.getLogger(__name__)


def _adjust_columns_widths(worksheet):
    """Adjust widths of columns in Excel worksheet.

    Parameters
    ----------
    worksheet: openpyxl worksheet

    Returns
    -------
        None

    Thanks to authors 'CharlesV' and 'oldsea' on SO:
    https://stackoverflow.com/questions/39529662/python-automatically-adjust-width-of-an-excel-files-columns

    """
    for col in worksheet.columns:
        max_length = 0

        for cell in col:
            try:  # Necessary to avoid error on empty cells
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        adjusted_width = (max_length + 2) * 1.2

        # Since Openpyxl 2.6, the column name is  ".column_letter" as .column became the column number (1-based)
        column = col[0].column_letter  # Get the column name
        worksheet.column_dimensions[column].width = adjusted_width



def _statisticByDate2dataframe(metric_ref):
    metric = Metric.objects.get(ref=metric_ref)
    statistics = StatisticByDate.objects.filter(metric=metric)

    dates = []
    values = []
    for l in statistics.values():
        dates.append(l['date'])
        values.append(l['value'])

    df = pd.DataFrame({'date': dates, metric.name: values})
    df.set_index('date', inplace=True)

    return df

def _statisticByDateAndObject2dataframe(metric_ref, content_type):
    """

    Parameters
    ----------
    metric_ref: str
        Reference string for metrics.

    content_type
        Objects of the given type needs to have a field 'name' which is unique.
        This is used as column name for the resulting dataframe.

    Returns
    -------
        DataFrame, with date as index and objects in columns

    """
    metric = Metric.objects.get(ref=metric_ref)
    statistics = StatisticByDateAndObject.objects.filter(metric=metric, object_type_id=content_type.id)

    values = []
    for l in statistics.values():

        # values.append(l['date'])
        obj = content_type.get_object_for_this_type(id=l['object_id'])
        obj_name = obj.name

        values.append({'date': l['date'], obj_name: l['value']})

    df = pd.DataFrame.from_records(values, index='date')
    df.fillna(0, inplace=True)
    return df


class Command(BaseCommand):
    help = "Exports a file with usage statistics."

    def handle(self, *args, **options):

        #
        # Compile results with single value for a date
        #
        login_count_df = _statisticByDate2dataframe('login_count')
        search_view_count_df = _statisticByDate2dataframe('search_view_count')
        statistics_by_date_df = pd.merge(login_count_df, search_view_count_df, on='date', how='outer')
        statistics_by_date_df.fillna(0, inplace=True)

        #
        # Compile results for statistics for objects
        #
        ct = ContentType.objects.get(model='analysisfunction')
        result_views_by_date_function_df = _statisticByDateAndObject2dataframe('analyses_results_view_count', ct)

        #
        # Write all dataframes to Excel file
        #
        with pd.ExcelWriter(EXPORT_FILE_NAME) as writer:
            statistics_by_date_df.to_excel(writer, sheet_name='statistics by date')
            result_views_by_date_function_df.to_excel(writer, sheet_name='views of analyses by date')

            for sheetname, sheet in writer.sheets.items():
                _adjust_columns_widths(sheet)


        self.stdout.write(self.style.SUCCESS(f"Written user statistics to file '{EXPORT_FILE_NAME}'."))
        _log.info("Done.")
