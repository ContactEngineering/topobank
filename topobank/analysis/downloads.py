"""
Views and helper functions for downloading analyses.
"""
import tempfile

import openpyxl
from openpyxl.worksheet.hyperlink import Hyperlink
from openpyxl.styles import PatternFill, Border, Side, Alignment, Protection, Font
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseBadRequest
from django.core.files.storage import default_storage
from django.contrib.contenttypes.models import ContentType

import pandas as pd
import io
import pickle
import numpy as np
import zipfile
import os.path
import textwrap

from .models import Analysis
from .views import CARD_VIEW_FLAVORS
from .utils import mangle_sheet_name
from ..manager.models import Surface


#######################################################################
# Download views
#######################################################################


def download_analyses(request, ids, card_view_flavor, file_format):
    """Returns a file comprised from analyses results.

    :param request:
    :param ids: comma separated string with analyses ids
    :param card_view_flavor: card view flavor, see CARD_VIEW_FLAVORS
    :param file_format: requested file format
    :return:
    """

    #
    # Check permissions and collect analyses
    #
    user = request.user
    if not user.is_authenticated:
        return HttpResponseForbidden()

    analyses_ids = [int(i) for i in ids.split(',')]

    analyses = []
    surface_ct = ContentType.objects.get_for_model(Surface)

    for aid in analyses_ids:
        analysis = Analysis.objects.get(id=aid)

        #
        # Check whether user has view permission for requested analysis
        #
        if not analysis.is_visible_for_user(user):
            return HttpResponseForbidden()

        #
        # Exclude analysis for surfaces having only one topography
        # (this is useful for averages - the only surface analyses so far -
        # and may be controlled by other means later, if needed)
        #
        if (analysis.subject_type == surface_ct) and (analysis.subject.num_topographies() <= 1):
            continue

        analyses.append(analysis)

    #
    # Check flavor and format argument
    #
    card_view_flavor = card_view_flavor.replace('_', ' ')  # may be given with underscore in URL
    if card_view_flavor not in CARD_VIEW_FLAVORS:
        return HttpResponseBadRequest("Unknown card view flavor '{}'.".format(card_view_flavor))

    download_response_functions = {
        ('plot', 'xlsx'): download_plot_analyses_to_xlsx,
        ('plot', 'txt'): download_plot_analyses_to_txt,
        ('roughness parameters', 'xlsx'): download_roughness_parameters_to_xlsx,
        ('roughness parameters', 'txt'): download_roughness_parameters_to_txt,
        ('contact mechanics', 'zip'): download_contact_mechanics_analyses_as_zip,
    }

    #
    # Dispatch
    #
    key = (card_view_flavor, file_format)
    if key not in download_response_functions:
        return HttpResponseBadRequest(
            "Cannot provide a download for card view flavor {} in file format ".format(card_view_flavor))

    return download_response_functions[key](request, analyses)


def _analyses_meta_data_dataframe(analyses, request):
    """Generates a pandas.DataFrame with meta data about analyses.

    Parameters
    ----------
    analyses:
        sequence of Analysis instances
    request:
        current request

    Returns
    -------
    pandas.DataFrame, can be inserted as extra sheet
    """

    properties = []
    values = []
    for i, analysis in enumerate(analyses):

        surface = analysis.related_surface
        pub = surface.publication if surface.is_published else None

        if i == 0:
            # list function name and a blank line
            properties = ["Function", ""]
            values = [str(analysis.function), ""]

        properties += ['Subject Type', 'Subject Name',
                       'Creator',
                       'Further arguments of analysis function', 'Start time of analysis task',
                       'End time of analysis task', 'Duration of analysis task']

        values += [str(analysis.subject.get_content_type().model), str(analysis.subject.name),
                   str(analysis.subject.creator),
                   analysis.get_kwargs_display(), str(analysis.start_time),
                   str(analysis.end_time), str(analysis.duration())]

        if analysis.configuration is None:
            properties.append("Versions of dependencies")
            values.append("Unknown. Please recalculate this analysis in order to have version information here.")
        else:
            versions_used = analysis.configuration.versions.order_by('dependency__import_name')

            for version in versions_used:
                properties.append(f"Version of '{version.dependency.import_name}'")
                values.append(f"{version.number_as_string()}")

        if pub:
            # If the surface of the topography was published, the URL is inserted
            properties.append("Publication URL (surface data)")
            values.append(request.build_absolute_uri(pub.get_absolute_url()))

        # We want an empty line on the properties sheet in order to distinguish the topographies
        properties.append("")
        values.append("")

    df = pd.DataFrame({'Property': properties, 'Value': values})

    return df


def _publications_urls(request, analyses):
    """Return set of publication URLS for given analyses.

    Parameters
    ----------
    request
        HTTPRequest
    analyses
        seq of Analysis instances
    Returns
    -------
    Set of absolute URLs (strings)
    """
    # Collect publication links, if any
    publication_urls = set()
    for a in analyses:
        surface = a.related_surface
        if surface.is_published:
            pub = surface.publication
            pub_url = request.build_absolute_uri(pub.get_absolute_url())
            publication_urls.add(pub_url)
    return publication_urls


def _analysis_header_for_txt_file(analysis, as_comment=True):
    """

    Parameters
    ----------
    analysis
        Analysis instance
    as_comment
        boolean, if True, add '# ' in front of each line

    Returns
    -------
    str
    """

    subject = analysis.subject
    subject_creator = subject.creator
    subject_type_str = analysis.subject_type.model.title()
    headline = f"{subject_type_str}: {subject.name}"

    s = f'{headline}\n' +\
        '='*len(headline) + '\n' +\
        f'Creator: {subject_creator}\n' +\
        f'Further arguments of analysis function: {analysis.get_kwargs_display()}\n' +\
        f'Start time of analysis task: {analysis.start_time}\n' +\
        f'End time of analysis task: {analysis.end_time}\n' +\
        f'Duration of analysis task: {analysis.duration()}\n'
    if analysis.configuration is None:
        s += 'Versions of dependencies (like "SurfaceTopography") are unknown for this analysis.\n'
        s += 'Please recalculate in order to have version information here.\n'
    else:
        versions_used = analysis.configuration.versions.order_by('dependency__import_name')

        for version in versions_used:
            s += f"Version of '{version.dependency.import_name}': {version.number_as_string()}\n"
    s += '\n'

    if as_comment:
        s = textwrap.indent(s, '# ', predicate=lambda s: True)  # prepend to all lines, also empty

    return s


def download_plot_analyses_to_txt(request, analyses):
    """Download plot data for given analyses as CSV file.

        Parameters
        ----------
        request
            HTTPRequest
        analyses
            Sequence of Analysis instances

        Returns
        -------
        HTTPResponse
    """
    # TODO: It would probably be useful to use the (some?) template engine for this.
    # TODO: We need a mechanism for embedding references to papers into output.

    # Collect publication links, if any
    publication_urls = _publications_urls(request, analyses)

    # Pack analysis results into a single text file.
    f = io.StringIO()
    for i, analysis in enumerate(analyses):
        if i == 0:
            f.write('# {}\n'.format(analysis.function) +
                    '# {}\n'.format('=' * len(str(analysis.function))))

            f.write('# IF YOU USE THIS DATA IN A PUBLICATION, PLEASE CITE XXX.\n' +
                    '\n')
            if len(publication_urls) > 0:
                f.write('#\n')
                f.write('# For these analyses, published data was used. Please visit these URLs for details:\n')
                for pub_url in publication_urls:
                    f.write(f'# - {pub_url}\n')
                f.write('#\n')

        f.write(_analysis_header_for_txt_file(analysis))

        result = pickle.loads(analysis.result)
        xunit_str = '' if result['xunit'] is None else ' ({})'.format(result['xunit'])
        yunit_str = '' if result['yunit'] is None else ' ({})'.format(result['yunit'])
        header = 'Columns: {}{}, {}{}'.format(result['xlabel'], xunit_str, result['ylabel'], yunit_str)

        std_err_y_in_series = any('std_err_y' in s.keys() for s in result['series'])
        if std_err_y_in_series:
            header += ', standard error of average {}{}'.format(result['ylabel'], yunit_str)
            f.writelines([
                '# The value "nan" for the standard error of an average indicates that no error\n',
                '# could be computed because the average contains only a single data point.\n\n'])

        for series in result['series']:
            series_data = [series['x'], series['y']]
            if std_err_y_in_series:
                try:
                    std_err_y = series['std_err_y']
                    if hasattr(std_err_y, 'filled'):
                        std_err_y = std_err_y.filled(np.nan)
                    series_data.append(std_err_y)
                except KeyError:
                    pass
            np.savetxt(f, np.transpose(series_data),
                       header='{}\n{}\n{}'.format(series['name'], '-' * len(series['name']), header))
            f.write('\n')

    # Prepare response object.
    response = HttpResponse(f.getvalue(), content_type='application/text')
    filename = '{}.txt'.format(analysis.function.name).replace(' ', '_')
    response['Content-Disposition'] = 'attachment; filename="{}"'.format(filename)

    # Close file and return response.
    f.close()
    return response


def download_plot_analyses_to_xlsx(request, analyses):
    """Download plot data for given analyses as XLSX file.

    Parameters
    ----------
    request
        HTTPRequest
    analyses
        Sequence of Analysis instances

    Returns
    -------
    HTTPResponse
    """
    # TODO: We need a mechanism for embedding references to papers into output.

    # Pack analysis results into a single text file.
    excel_file_buffer = io.BytesIO()
    excel_writer = pd.ExcelWriter(excel_file_buffer)
    bold_font = Font(bold=True)

    #
    # Create sheet with meta data
    #
    meta_df = _analyses_meta_data_dataframe(analyses, request)
    meta_df.to_excel(excel_writer, sheet_name='INFORMATION', index=False, freeze_panes=(1, 0))

    # Analyze subject names and store a distinct name
    # which can be used in sheet names if subject names are not unique
    subject_names_in_sheet_names = [a.subject.name for a in analyses]

    for sn in set(subject_names_in_sheet_names):  # iterate over distinct names

        # replace name with a unique one using a counter
        indices = [i for i, a in enumerate(analyses) if a.subject.name == sn]

        if len(indices) > 1:  # only rename if not unique
            for k, idx in enumerate(indices):
                subject_names_in_sheet_names[idx] += f" ({k + 1})"

    def comment_on_average(y, std_err_y_masked):
        """Calculate a comment.

        Parameters:
            y: float
            std_err_y_masked: boolean
        """
        if np.isnan(y):
            return 'average could not be computed'
        elif std_err_y_masked:
            return 'no error could be computed because the average contains only a single data point'
        return ''

    index_entries = []  # tuples with (subject name, subject type, function name, data series, hyperlink to sheet)

    for analysis_idx, analysis in enumerate(analyses):
        result = pickle.loads(analysis.result)
        column1 = '{} ({})'.format(result['xlabel'], result['xunit'])
        column2 = '{} ({})'.format(result['ylabel'], result['yunit'])
        column3 = 'standard error of {} ({})'.format(result['ylabel'], result['yunit'])
        column4 = 'comment'

        for series_idx, series in enumerate(result['series']):
            df_columns_dict = {column1: series['x'], column2: series['y']}
            try:
                std_err_y_mask = series['std_err_y'].mask
            except (AttributeError, KeyError) as exc:
                std_err_y_mask = np.zeros(series['y'].shape, dtype=bool)

            try:
                df_columns_dict[column3] = series['std_err_y']
                df_columns_dict[column4] = [comment_on_average(y, masked)
                                            for y, masked in zip(series['y'], std_err_y_mask)]
            except KeyError:
                pass
            df = pd.DataFrame(df_columns_dict)

            #
            # Save data for index entry
            #
            sheet_name = f"analysis-{analysis_idx}-series-{series_idx}"

            subject_type = analysis.subject.get_content_type().name  # human-readable name
            if subject_type == 'topography':
                subject_type = 'measurement'  # this is how topographies are denoted in the UI
            index_entries.append((analysis.subject.name, subject_type,
                                  analysis.function.name, series['name'], sheet_name))

            #
            # Write data sheet to excel file
            #
            df.to_excel(excel_writer, sheet_name=sheet_name, freeze_panes=(6, 1), startcol=0, startrow=5)
            sheet = excel_writer.sheets[sheet_name]
            sheet["A1"] = "Analysis"
            sheet["A1"].font = bold_font
            sheet["B1"] = analysis.function.name
            sheet["A2"] = "Subject"
            sheet["A2"].font = bold_font
            sheet["B2"] = analysis.subject.name
            sheet["A3"] = "Subject Type"
            sheet["A3"].font = bold_font
            sheet["B3"] = subject_type
            sheet["A4"] = "Data Series"
            sheet["A4"].font = bold_font
            sheet["B4"] = series['name']
            sheet.column_dimensions['A'].width = 20
            sheet.column_dimensions['B'].width = 20
            sheet.column_dimensions['C'].width = 20
            sheet.column_dimensions['D'].width = 25

            # Link "Back to Index"
            sheet["D1"].hyperlink = Hyperlink(ref=f"D1",
                                              location="'INDEX'!A1",
                                              tooltip=f"Click to jump back to INDEX")
            sheet["D1"].value = "Click to jump back to INDEX"
            sheet["D1"].style = "Hyperlink"



    excel_writer.close()

    filename = '{}.xlsx'.format(analysis.function.name).replace(' ', '_')
    #
    # Create INDEX sheet with links in Openpyxl
    #
    wb = openpyxl.load_workbook(excel_file_buffer)
    excel_file_buffer.close()

    index_ws = wb.create_sheet("INDEX", 0)

    index_headers = ["Subject Name", "Subject Type", "Function Name", "Data Series", "Link"]
    for col_idx, col_header in enumerate(index_headers):
        header_cell = index_ws.cell(row=1, column=col_idx+1)
        header_cell.value = col_header
        header_cell.font = bold_font

    def create_index_entry(row, index_entry):
        """Create a row on the index sheet."""
        subject_name, subject_type, function_name, data_series, sheet_name = index_entry
        index_ws.cell(row=row, column=1).value = subject_name
        index_ws.cell(row=row, column=2).value = subject_type
        index_ws.cell(row=row, column=3).value = function_name
        index_ws.cell(row=row, column=4).value = data_series
        hyperlink_cell = index_ws.cell(row=row, column=5)
        hyperlink_label = f"Click to jump to sheet '{sheet_name}'"
        hyperlink_location = f"'{sheet_name}'!B2"  # don't use # here before sheet name, does not work

        # Hyperlink class: target keyword seems to be used for external links
        # hyperlink_cell.value = f'=HYPERLINK("{hyperlink_location}", "{hyperlink_label}")'
        # didn't manage to get it working with HYPERLINK function
        hyperlink_cell.value = hyperlink_label
        hyperlink_cell.hyperlink = Hyperlink(ref=f"E{row}",
                                             location=hyperlink_location,
                                             tooltip=f"Click to jump to sheet '{sheet_name}' with data")
        hyperlink_cell.style = "Hyperlink"

    for entry_idx, index_entry in enumerate(index_entries):
        create_index_entry(entry_idx+2, index_entry)
    # create_index_entry(len(index_entries) + 2, ("META DATA", '', '', '', 'META DATA'))

    # increase column width on index page
    for col, colwidth in [("A", 30), ("B", 15), ("C", 25), ("D", 30), ("E", 45)]:
        index_ws.column_dimensions[col].width = colwidth

    #
    # Save to named temporary file and prepare response
    #
    with tempfile.NamedTemporaryFile() as tmp:
        wb.save(tmp.name)
        tmp.seek(0)

        response = HttpResponse(tmp.read(),
                                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    response['Content-Disposition'] = 'attachment; filename="{}"'.format(filename)

    return response


def download_roughness_parameters_to_txt(request, analyses):
    """Download roughness parameters from given analyses as CSV file.

       Tables with roughness parameters only make sense for analyses
       where subject is a topography (so far). All other analyses
       (e.g. for surfaces) will be ignored here.

        Parameters
        ----------
        request
            HTTPRequest
        analyses
            Sequence of Analysis instances

        Returns
        -------
        HTTPResponse
    """
    # TODO: It would probably be useful to use the (some?) template engine for this.
    # TODO: We need a mechanism for embedding references to papers into output.

    # Only use analyses which are related to a specific topography
    analyses = [a for a in analyses if a.is_topography_related]

    # Collect publication links, if any
    publication_urls = _publications_urls(request, analyses)

    # Pack analysis results into a single text file.
    data = []
    f = io.StringIO()
    for i, analysis in enumerate(analyses):
        if i == 0:
            f.write('# {}\n'.format(analysis.function) +
                    '# {}\n'.format('=' * len(str(analysis.function))))

            f.write('# IF YOU USE THIS DATA IN A PUBLICATION, PLEASE CITE XXX.\n' +
                    '#\n')
            if len(publication_urls) > 0:
                f.write('#\n')
                f.write('# For these analyses, published data was used. Please visit these URLs for details:\n')
                for pub_url in publication_urls:
                    f.write(f'# - {pub_url}\n')
                f.write('#\n')

        f.write(_analysis_header_for_txt_file(analysis))

        result = pickle.loads(analysis.result)
        topography = analysis.subject
        for row in result:
            data.append([topography.surface.name,
                         topography.name,
                         row['quantity'],
                         row['direction'] if row['direction'] else '',
                         row['from'] if row['from'] else '',
                         row['symbol'] if row['symbol'] else '',
                         row['value'],
                         row['unit']])

    f.write('# Table of roughness parameters\n')
    df = pd.DataFrame(data, columns=['surface', 'measurement', 'quantity', 'direction',
                                     'from', 'symbol', 'value', 'unit'])
    df.to_csv(f, index=False)
    f.write('\n')

    # Prepare response object.
    response = HttpResponse(f.getvalue(), content_type='application/text')
    filename = '{}.txt'.format(analysis.function.name.replace(' ', '_'))
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    # Close file and return response.
    f.close()
    return response


def download_roughness_parameters_to_xlsx(request, analyses):
    """Download roughness parameters from given analyses as XLSX file.

       Tables with roughness parameters only make sense for analyses
       where subject is a topography (so far). All other analyses
       (e.g. for surfaces) will be ignored here.

        Parameters
        ----------
        request
            HTTPRequest
        analyses
            Sequence of Analysis instances

        Returns
        -------
        HTTPResponse
    """
    analyses = [a for a in analyses if a.is_topography_related]

    f = io.BytesIO()
    excel = pd.ExcelWriter(f)

    data = []
    for analysis in analyses:
        topo = analysis.subject
        for row in pickle.loads(analysis.result):
            row['surface'] = topo.surface.name
            row['measurement'] = topo.name
            data.append(row)

    roughness_df = pd.DataFrame(data, columns=['surface', 'measurement', 'quantity', 'direction',
                                               'from', 'symbol', 'value', 'unit'])
    roughness_df.replace(r'&Delta;', 'Δ', inplace=True, regex=True)  # we want a real greek delta
    roughness_df.to_excel(excel, sheet_name="Roughness parameters", index=False)
    info_df = _analyses_meta_data_dataframe(analyses, request)
    info_df.to_excel(excel, sheet_name='INFORMATION', index=False)
    excel.close()

    # Prepare response object.
    response = HttpResponse(f.getvalue(),
                            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    filename = '{}.xlsx'.format(analysis.function.name.replace(' ', '_'))
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    # Close file and return response.
    f.close()
    return response


def download_contact_mechanics_analyses_as_zip(request, analyses):
    """Provides a ZIP file with contact mechanics data.

    :param request: HTTPRequest
    :param analyses: sequence of Analysis instances
    :return: HTTP Response with file download
    """

    bytes = io.BytesIO()

    zf = zipfile.ZipFile(bytes, mode='w')

    #
    # Add directories and files for all analyses
    #
    zip_dirs = set()

    for analysis in analyses:

        zip_dir = analysis.subject.name
        if zip_dir in zip_dirs:
            # make directory unique
            zip_dir += "-{}".format(analysis.subject.id)
        zip_dirs.add(zip_dir)

        #
        # Add a csv file with plot data
        #
        analysis_result = analysis.result_obj

        col_keys = ['mean_pressures', 'total_contact_areas', 'mean_gaps', 'converged', 'data_paths']
        col_names = ["Normalized pressure p/E*", "Fractional contact area A/A0", "Normalized mean gap u/h_rms",
                     "converged", "filename"]

        col_dicts = {col_names[i]: analysis_result[k] for i, k in enumerate(col_keys)}
        plot_df = pd.DataFrame(col_dicts)
        plot_df['filename'] = plot_df['filename'].map(lambda fn: os.path.split(fn)[1])  # only simple filename

        plot_filename_in_zip = os.path.join(zip_dir, 'plot.csv')
        zf.writestr(plot_filename_in_zip, plot_df.to_csv())

        #
        # Add nc files from storage
        #
        prefix = analysis.storage_prefix

        directories, filenames = default_storage.listdir(prefix)

        for dirname in directories:
            # each directory corresponds to a step
            input_file = default_storage.open(f"{prefix}/{dirname}/nc/results.nc")

            filename_in_zip = os.path.join(zip_dir, f"result-{dirname}.nc")

            try:
                zf.writestr(filename_in_zip, input_file.read())
            except Exception as exc:
                zf.writestr("errors-{}.txt".format(dirname),
                            "Cannot save file {} in ZIP, reason: {}".format(filename_in_zip, str(exc)))

        #
        # Add a file with version information
        #
        zf.writestr(os.path.join(zip_dir, 'info.txt'),
                    _analysis_header_for_txt_file(analysis))


    #
    # Add a Readme file
    #
    zf.writestr("README.txt",
                f"""
Contents of this ZIP archive
============================
This archive contains data from contact mechanics calculation.

Each directory corresponds to one measurement and is named after the measurement.
Inside you find two types of files:

- a simple CSV file ('plot.csv')
- a couple of classical netCDF files (Extension '.nc')

The file 'plot.csv' contains a table with the data used in the plot,
one line for each calculation step. It has the following columns:

- Zero-based index column
- Normalized pressure in units of p/E*
- Fractional contact area in units of A/A0
- Normalized mean gap in units of u/h_rms
- A boolean flag (True/False) which indicates whether the calculation converged
  within the given limit
- Filename of the NetCDF file (order of filenames may be different than index)

So each line also refers to one NetCDF file in the directory, it corresponds to
one external pressure. Inside the NetCDF file you'll find the variables

* `contact_points`: boolean array, true if point is in contact
* `pressure`: floating-point array containing local pressure (in units of `E*`)
* `gap`: floating-point array containing the local gap
* `displacement`: floating-point array containing the local displacements

as well as the attributes

* `mean_pressure`: mean pressure (in units of `E*`)
* `total_contact_area`: total contact area (fractional)

Accessing the CSV file
======================

Inside the archive you find a file "plot.csv" which contains the data
from the plot.

With Python and numpy you can load it e.g. like this:

```
import numpy as np
pressure_contact_area = np.loadtxt("plot.csv", delimiter=",",
                                   skiprows=1, usecols=(1,2))
```

With pandas, you can do:

```
import pandas as pd
df = pd.read_csv("plot.csv", index_col=0)
```

Accessing the NetCDF files
==========================

In order to read the data for each point,
you can use a netCDF library. Please see the following examples:

### Python

Given the package [`netcdf4-python`](http://netcdf4-python.googlecode.com/) is installed:

```
import netCDF4
ds = netCDF4.Dataset("result-step-0.nc")
print(ds)
pressure = ds['pressure'][:]
mean_pressure = ds.mean_pressure
```

Another convenient package you can use is [`xarray`](xarray.pydata.org/).

### Matlab

In order to read the pressure map in Matlab, use

```
ncid = netcdf.open("result-step-0.nc", 'NC_NOWRITE');
varid = netcdf.inqVarID(ncid, "pressure");
pressure = netcdf.getVar(ncid, varid);
```

Have look in the official Matlab documentation for more information.

Version information
===================

For version information of the packages used, please look into the files named
'info.txt' in the subdirectories for each measurement. The versions of the packages
used for analysis may differ among measurements, because they may have been
calculated at different times.
    """)

    zf.close()

    # Prepare response object.
    response = HttpResponse(bytes.getvalue(),
                            content_type='application/x-zip-compressed')
    response['Content-Disposition'] = 'attachment; filename="{}"'.format('contact_mechanics.zip')

    return response
