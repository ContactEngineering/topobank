import logging

import numpy as np
import pandas as pd
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.db.models import Count
from trackstats.models import Metric, StatisticByDate, StatisticByDateAndObject

from topobank.manager.models import Surface, Topography
from topobank.usage_stats.utils import register_metrics

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
            # noinspection PyBroadException
            try:  # Necessary to avoid error on empty cells
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:  # noqa: E722
                pass

        adjusted_width = (max_length + 2) * 1.2

        # Since Openpyxl 2.6, the column name is  ".column_letter" as .column became the column number (1-based)
        column = col[0].column_letter  # Get the column name
        worksheet.column_dimensions[column].width = adjusted_width


def _empty_date_dataframe(columns=[]):
    columns = ['date'] + columns
    return pd.DataFrame(columns=columns).set_index('date')


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
    for stat_entry in statistics.values():
        dates.append(stat_entry['date'])
        values.append(stat_entry['value'])

    if column_heading is None:
        column_heading = metric.name

    df = pd.DataFrame({'date': dates, column_heading: values})
    df['date'] = pd.to_datetime(df['date'])
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
    for L in statistics.values():

        # _log.info("Getting statistics value for %s..", l)
        try:
            obj = content_type.get_object_for_this_type(id=L['object_id'])
            obj_name = getattr(obj, attr_name)
            values.append({'date': L['date'], obj_name: L['value']})
        except ObjectDoesNotExist:
            _log.warning("Cannot find object with id %s, content_type '%s', but it is listed in statistics. Ignoring.",
                         L['object_id'], content_type)

    if values:
        df = pd.DataFrame.from_records(values, index='date').groupby('date').sum()
        df.fillna(0, inplace=True)
        df.sort_index(ascending=False, inplace=True)
        return df
    else:
        _log.warning("No usable values for statistics for metric '%s'.", metric_ref)
        return _empty_date_dataframe()


def make_excel():
    def last_value_func(x):
        return x.iloc[-1] if len(x) > 0 else np.nan

    #
    # Compile results with single value for a date
    #
    # Elements: (metric_ref, factor, column_heading or None for default, aggregation function)
    #
    single_value_metrics = [
        ('login_count', 1, 'Number of users having logged in', np.sum),
        ('total_request_count', 1, 'Total number of requests of any kind', np.sum),
        ('search_view_count', 1, 'Number of views for Search page', np.sum),
        ('total_analysis_cpu_ms', .001 / 60 / 60, 'Total analysis CPU time in hours', np.sum),
        ('total_number_users', 1, 'Total number of registered users', last_value_func),
        ('total_number_surfaces', 1, 'Total number of surfaces', last_value_func),
        ('total_number_topographies', 1, 'Total number of topographies', last_value_func),
        ('total_number_analyses', 1, 'Total number of analyses', last_value_func),
    ]

    statistics_by_date_df = pd.DataFrame({'date': []}).set_index('date')

    for metric_ref, factor, column_heading, agg_func in single_value_metrics:
        metric_df = factor * _statisticByDate2dataframe(metric_ref,
                                                        column_heading=column_heading)
        if len(metric_df) > 0:
            statistics_by_date_df = pd.merge(statistics_by_date_df,
                                             metric_df,
                                             on='date', how='outer')
        else:
            # add column with NaN
            if column_heading is None:
                column_heading = metric_ref
            statistics_by_date_df[column_heading] = np.nan

    statistics_by_date_df.fillna(0, inplace=True)
    statistics_by_date_df.sort_index(ascending=False, inplace=True)  # we want to have it sorted by date

    #
    # Compile summary for sheet statistics_by_date
    #
    if statistics_by_date_df.empty:
        summary_df = pd.DataFrame()
    else:
        summary_groups = statistics_by_date_df.reset_index().groupby(pd.Grouper(key='date', axis=0, freq='M'))

        summary_df = summary_groups.aggregate({column_heading: agg_func
                                               for metric_ref, factor, column_heading, agg_func
                                               in single_value_metrics})

        # sort columns
        column_order = [ch for _, _, ch, _ in single_value_metrics]
        summary_df = summary_df[column_order]

        # Replacing long descriptive names with short names in summary
        summary_df.rename(columns={
            'Number of users having logged in': 'logins',
            'Total number of requests of any kind': 'any requests',
            'Number of views for Search page': 'search page requests',
            'Total analysis CPU time in hours': 'analysis CPU hours',
            'Total number of registered users': 'registered users',
            'Total number of surfaces': 'surfaces',
            'Total number of topographies': 'measurements',
            'Total number of analyses': 'analyses',
        }, inplace=True)
        summary_df.index.names = ['month']
        summary_df.index = summary_df.index.to_period("M")
        summary_df.sort_index(ascending=False, inplace=True)

    #
    # Compile distribution of measurements over users
    #
    measurement_dist_qs = Topography.objects.values('creator').annotate(meas_count=Count('creator')).order_by(
        '-meas_count')
    measurement_dist_df = pd.DataFrame.from_records(measurement_dist_qs)
    if not measurement_dist_df.empty:
        surface_dist_qs = Surface.objects.values('creator').annotate(surf_count=Count('creator')).order_by(
            '-surf_count')
        surface_dist_df = pd.DataFrame.from_records(surface_dist_qs)
        measurement_dist_df = measurement_dist_df.merge(surface_dist_df, on='creator', how='left')
        del measurement_dist_df['creator']
        measurement_dist_df.sort_values('meas_count', ascending=False)
        measurement_dist_df.rename(columns={'meas_count': 'number of measurement uploads',
                                            'surf_count': 'number of surfaces'},
                                   inplace=True)
        measurement_dist_df.index.rename('rank', inplace=True)
        measurement_dist_df.index += 1  # we want the index start with 1

    #
    # Compile results for statistics for objects
    #
    ct_af = ContentType.objects.get(model='workflow')
    result_views_by_date_function_df = _statisticByDateAndObject2dataframe('analyses_results_view_count', ct_af)
    analysis_cpu_seconds_by_date_function_df = _statisticByDateAndObject2dataframe('total_analysis_cpu_ms',
                                                                                   ct_af) / 1000

    try:
        ct_pub = ContentType.objects.get(model='publication')
        publication_views_by_date_function_df = _statisticByDateAndObject2dataframe('publication_view_count', ct_pub,
                                                                                    'short_url')
    except ContentType.DoesNotExist:
        publication_views_by_date_function_df = None

    ct_surf = ContentType.objects.get(model='surface')
    surface_views_by_date_function_df = _statisticByDateAndObject2dataframe('surface_view_count', ct_surf, 'id')
    surface_downloads_by_date_function_df = _statisticByDateAndObject2dataframe('surface_download_count',
                                                                                ct_surf, 'id')

    #
    # Write all dataframes to Excel file
    #
    with pd.ExcelWriter(EXPORT_FILE_NAME) as writer:
        summary_df.to_excel(writer, sheet_name='summary')
        measurement_dist_df.to_excel(writer, sheet_name='upload distribution over users')
        statistics_by_date_df.to_excel(writer, sheet_name='statistics by date')
        result_views_by_date_function_df.to_excel(writer, sheet_name='analysis views by date+function')
        analysis_cpu_seconds_by_date_function_df.to_excel(writer, sheet_name='cpu seconds by date+function')
        if publication_views_by_date_function_df is not None:
            publication_views_by_date_function_df.to_excel(writer, sheet_name='publication req. by date+url')
        surface_views_by_date_function_df.to_excel(writer, sheet_name='surface views by date+id')
        surface_downloads_by_date_function_df.to_excel(writer, sheet_name='surface downloads by date+id')
        for sheetname, sheet in writer.sheets.items():
            _adjust_columns_widths(sheet)

        # Do some more formatting on summary sheet
        summary_sheet = writer.sheets['summary']
        # cell ranges
        index_column = 'A'
        # value_cells = 'B2:{col}{row}'.format(
        #     col=get_column_letter(summary_sheet.max_column),
        #     row=summary_sheet.max_row)
        # title_row = '1'

        # index column width
        summary_sheet.column_dimensions[index_column].width = 21

        # for general styling, one has to iterate over
        # all cells individually
        CPU_cells = 'E2:E{row}'.format(
            row=summary_sheet.max_row)
        for row in summary_sheet[CPU_cells]:
            for cell in row:
                cell.number_format = '0.00'

        index_cells = 'A2:A{row}'.format(
            row=summary_sheet.max_row)
        for row in summary_sheet[index_cells]:
            for cell in row:
                cell.number_format = 'yyyy-mm'


class Command(BaseCommand):
    help = "Exports a file with usage statistics."

    def add_arguments(self, parser):
        parser.add_argument('-s', '--send-email', nargs='+', type=str,
                            help="Send statistics as mail attachment to given address.")

    def handle(self, *args, **options):

        register_metrics()

        #
        # Compile Dataframe for "summary" sheet (see GH #572)
        #
        # summary_df = pd.DataFrame({'month': []}).set_index('month')

        # Shows the data by month, with the current month at the top, and going
        # reverse-chronologically back to the creation month at the bottom.
        # Show a monthly cumulative total for each of the "summable" numbers (logins by users,
        # analyses requested, etc.).
        # Show a monthly snapshot number for any non-cumulative numbers like total number of users.
        # Use narrow columns.

        # columns = [
        #     'new logins',
        #     'requests',
        #     'select page req',
        #     'analysis CPU secs',
        #     'registered users',
        #     'surfaces',
        #     'measurements',
        #     'analyses'
        # ]
        make_excel()

        self.stdout.write(self.style.SUCCESS(f"Written user statistics to file '{EXPORT_FILE_NAME}'."))

        if options['send_email']:
            recipients = options['send_email']
            self.stdout.write(self.style.NOTICE(f"Trying to send file '{EXPORT_FILE_NAME}' to {recipients}.."))

            import textwrap

            email_body = textwrap.dedent("""
            Hi,

            As attachment you'll find a spreadsheet with current usage statistics for
            the website 'contact.engineering'.

            This mail was automatically generated.

            Take care!
            """)

            email = EmailMessage(
                'Usage statistics about contact.engineering',
                email_body,
                settings.CONTACT_EMAIL_ADDRESS,
                recipients,
                reply_to=[settings.CONTACT_EMAIL_ADDRESS],
                attachments=[
                    (EXPORT_FILE_NAME, open(EXPORT_FILE_NAME, mode='rb').read(), 'application/vnd.ms-excel')
                ]
            )

            # email.attach(EXPORT_FILE_NAME)

            try:
                email.send()
                self.stdout.write(self.style.SUCCESS("Mail was sent successfully."))
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"Could not send statistics to {recipients}. Reason: {exc}"))

        _log.info("Done.")
