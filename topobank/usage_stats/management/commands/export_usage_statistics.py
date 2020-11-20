from django.core.management.base import BaseCommand
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist

from trackstats.models import Metric, StatisticByDate, StatisticByDateAndObject
from topobank.usage_stats.utils import register_metrics

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


def _empty_date_dataframe():
    return pd.DataFrame(columns=['date']).set_index('date')


def _statisticByDate2dataframe(metric_ref, column_heading=None):
    """

    Parameters
    ----------
    metric_ref: str
        Reference of metric.
    column_heading: str, optional
        Column heading used in dataframe. Use
        name of metric, if not given.

    Returns
    -------
    DataFrame with index 'date'

    """
    try:
        metric = Metric.objects.get(ref=metric_ref)
    except Metric.DoesNotExist:
        _log.warning("No data for metric '%s'.", metric_ref)
        return _empty_date_dataframe()

    statistics = StatisticByDate.objects.filter(metric=metric)

    dates = []
    values = []
    for l in statistics.values():
        dates.append(l['date'])
        values.append(l['value'])

    if column_heading is None:
        column_heading = metric.name

    df = pd.DataFrame({'date': dates, column_heading: values})
    df.set_index('date', inplace=True)

    return df


def _statisticByDateAndObject2dataframe(metric_ref, content_type, attr_name='name'):
    """

    Parameters
    ----------
    metric_ref: str
        Reference string for metrics.

    content_type: ContentType instance
        Objects of the given type needs to have a attribute named 'attr_name'
        This is used as column name for the resulting dataframe.

    attr_name: str
        Name of the attribute to display

    Returns
    -------
        DataFrame, with date as index and objects in columns

    """
    try:
        metric = Metric.objects.get(ref=metric_ref)
    except Metric.DoesNotExist:
        _log.warning("No data for metric '%s'.", metric_ref)
        return _empty_date_dataframe()

    statistics = StatisticByDateAndObject.objects.filter(metric=metric, object_type_id=content_type.id)

    values = []
    for l in statistics.values():

        # _log.info("Getting statistics value for %s..", l)
        try:
            obj = content_type.get_object_for_this_type(id=l['object_id'])
            obj_name = getattr(obj, attr_name)
            values.append({'date': l['date'], obj_name: l['value']})
        except ObjectDoesNotExist:
            _log.warning("Cannot find object with id %s, content_type '%s', but it is listed in statistics. Ignoring.",
                         l['object_id'], content_type)

    if values:
        df = pd.DataFrame.from_records(values, index='date').groupby('date').sum()
        df.fillna(0, inplace=True)
        return df
    else:
        _log.warning("No usable values for statistics for metric '%s'.", metric_ref)
        return _empty_date_dataframe()


class Command(BaseCommand):
    help = "Exports a file with usage statistics."

    def handle(self, *args, **options):

        register_metrics()

        #
        # Compile results with single value for a date
        #
        single_value_metrics = [
            ('login_count', 1, None),
            ('search_view_count', 1, None),
            ('total_analysis_cpu_ms', .001, 'Total analysis CPU time in seconds'),
            ('total_number_users', 1, None),
            ('total_number_surfaces', 1, None),
            ('total_number_topographies', 1, None),
            ('total_number_analyses', 1, None),
        ]

        statistics_by_date_df = pd.DataFrame({'date': []}).set_index('date')

        for metric_ref, factor, column_heading in  single_value_metrics:
            metric_df = factor * _statisticByDate2dataframe(metric_ref,
                                                            column_heading=column_heading)
            statistics_by_date_df = pd.merge(statistics_by_date_df,
                                             metric_df,
                                             on='date', how='outer')

        statistics_by_date_df.fillna(0, inplace=True)

        #
        # Compile results for statistics for objects
        #
        ct_af = ContentType.objects.get(model='analysisfunction')
        result_views_by_date_function_df = _statisticByDateAndObject2dataframe('analyses_results_view_count', ct_af)
        analysis_cpu_seconds_by_date_function_df = _statisticByDateAndObject2dataframe('total_analysis_cpu_ms', ct_af)/1000

        ct_pub = ContentType.objects.get(model='publication')
        publication_views_by_date_function_df = _statisticByDateAndObject2dataframe('publication_view_count', ct_pub,
                                                                                    'short_url')

        ct_surf = ContentType.objects.get(model='surface')
        surface_views_by_date_function_df = _statisticByDateAndObject2dataframe('surface_view_count', ct_surf, 'id')
        surface_downloads_by_date_function_df = _statisticByDateAndObject2dataframe('surface_download_count',
                                                                                    ct_surf, 'id')

        #
        # Write all dataframes to Excel file
        #
        with pd.ExcelWriter(EXPORT_FILE_NAME) as writer:
            statistics_by_date_df.to_excel(writer, sheet_name='statistics by date')
            result_views_by_date_function_df.to_excel(writer, sheet_name='analysis views by date+function')
            analysis_cpu_seconds_by_date_function_df.to_excel(writer, sheet_name='cpu seconds by date+function')
            publication_views_by_date_function_df.to_excel(writer, sheet_name='publication req. by date+url')
            surface_views_by_date_function_df.to_excel(writer, sheet_name='surface views by date+id')
            surface_downloads_by_date_function_df.to_excel(writer, sheet_name='surface downloads by date+id')
            for sheetname, sheet in writer.sheets.items():
                _adjust_columns_widths(sheet)

        self.stdout.write(self.style.SUCCESS(f"Written user statistics to file '{EXPORT_FILE_NAME}'."))
        _log.info("Done.")
