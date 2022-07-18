import io
import zipfile
import os.path

import pandas as pd
from django.core.files.storage import default_storage
from django.http import HttpResponse

from topobank.analysis.downloads import analysis_header_for_txt_file
from topobank.analysis.registry import register_download_function
from .functions import ART_CONTACT_MECHANICS

@register_download_function(ART_CONTACT_MECHANICS, 'results', 'zip')
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
        analysis_result = analysis.result

        col_keys = ['mean_pressures', 'total_contact_areas', 'mean_gaps', 'converged', 'data_paths']
        col_names = ["Normalized pressure p/E*", "Fractional contact area A/A0", "Normalized mean gap u/h_rms",
                     "converged", "filename"]

        col_dicts = {col_names[i]: analysis_result[k] for i, k in enumerate(col_keys)}
        plot_df = pd.DataFrame(col_dicts)
        plot_df['filename'] = "result-" + plot_df['filename'].map(lambda fn: os.path.split(fn)[1]) + ".nc"
        # only simple filename

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
                    analysis_header_for_txt_file(analysis))


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
