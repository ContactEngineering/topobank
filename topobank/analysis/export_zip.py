"""
Bundling of workflow results into a ZIP archive for download.

Result files live in the object store and are normally handed to the client
directly (as pre-signed URLs), so no bundling is needed to look at a result.
Downloading a whole result is different: a single contact-mechanics result, for
example, holds one NetCDF file per pressure step, each carrying grid-sized
arrays. Archives are therefore assembled by a Celery worker (see
`ResultZipContainer`) and streamed file by file, so that neither the archive nor
any single member is ever held in memory in full.
"""

import logging
import os.path
import shutil
import zipfile

from django.utils.text import slugify

_log = logging.getLogger(__name__)

#: Directories inside a result folder that hold display-only artifacts and are
#: skipped when bundling. Deep-zoom images are a tile pyramid rendered for the
#: web viewer from data that is also present in the archived NetCDF files;
#: including them would add thousands of small files per result.
EXCLUDED_DIRECTORIES = ["dzi"]

README = """\
Contents of this ZIP archive
============================

This archive contains the results of {nb_results} analysis (or analyses) run on
contact.engineering.

Each directory corresponds to one analyzed subject (a measurement, a dataset or
a tag) and is named after it. Inside each directory you find:

- 'info.txt', describing what was calculated, with which parameters, and which
  versions of which packages were used. If the data is published, please cite
  the papers listed there.
- the result files of the analysis themselves. 'result.json' holds the summary
  result and the metadata of the data series; larger arrays are stored
  alongside it as further JSON files or as classic NetCDF files (extension
  '.nc').

Reading the files
=================

JSON files can be read with Python's built-in `json` module:

```
import json
with open("result.json") as f:
    result = json.load(f)
```

Note that JSON has no representation for "not a number"; such values are
written as `null`.

NetCDF files can be read with the `netcdf4-python` or `xarray` packages:

```
import xarray
ds = xarray.load_dataset("results.nc")
```

In Matlab, use:

```
ncid = netcdf.open("results.nc", 'NC_NOWRITE');
varid = netcdf.inqVarID(ncid, "pressure");
pressure = netcdf.getVar(ncid, varid);
```

Please see the official documentation of those packages for details.
"""


def _versions_text(result) -> str:
    """Describe the versions of the packages used to compute `result`."""
    if result.configuration is None:
        return (
            "Versions of dependencies are unknown for this analysis.\n"
            "Please recalculate it in order to have version information here.\n"
        )
    s = ""
    for version in result.configuration.versions.order_by("dependency__import_name"):
        s += f"Version of '{version.dependency.import_name}': {version.number_as_string()}\n"
    return s


def result_info_text(result) -> str:
    """
    Describe a workflow result in human-readable form: what was computed, on
    what, with which parameters, and with which versions of which packages.

    Parameters
    ----------
    result : topobank.analysis.models.WorkflowResult
        The result to describe.

    Returns
    -------
    str
        The description, suitable for writing to a text file.
    """
    subject = result.subject
    workflow = result.function
    headline = f"{subject._meta.model_name}: {subject.name}"

    s = f"{headline}\n{'=' * len(headline)}\n"
    s += f"Analysis: {workflow.display_name if workflow is not None else 'unknown'}\n"
    for attribute, label in [
        ("created_by", "Creator"),
        ("instrument_name", "Instrument name"),
        ("instrument_type", "Instrument type"),
        ("instrument_parameters", "Instrument parameters"),
    ]:
        if hasattr(subject, attribute):
            s += f"{label}: {getattr(subject, attribute)}\n"
    s += (
        f"Further arguments of analysis function: {result.kwargs}\n"
        f"Start time of analysis task: {result.task_start_time}\n"
        f"End time of analysis task: {result.task_end_time}\n"
        f"Duration of analysis task: {result.task_duration}\n"
    )
    s += _versions_text(result)

    if result.dois:
        s += "\nIF YOU USE THIS DATA IN A PUBLICATION, PLEASE CITE THE FOLLOWING PAPERS:\n"
        for doi in result.dois:
            s += f"- {doi}\n"

    return s


def _readme_text(results) -> str:
    """Assemble the archive README, including any workflow-specific sections."""
    s = README.format(nb_results=len(results))

    # Workflows may document their own output files by declaring
    # `Meta.download_readme`; each distinct section is appended once.
    sections = {}
    for result in results:
        implementation = result.implementation
        if implementation is None:
            continue
        section = getattr(implementation.Meta, "download_readme", None)
        if section is not None:
            sections[implementation.Meta.name] = section
    for section in sections.values():
        s += f"\n\n{section.strip()}\n"

    return s


def _directory_names(results) -> list[str]:
    """
    Name one archive directory per result, after the analyzed subject. Names are
    disambiguated with the result id where subjects share a name, so that no
    result silently overwrites another.
    """
    names = [slugify(result.subject.name) or f"result-{result.id}" for result in results]
    counts = {}
    for name in names:
        counts[name] = counts.get(name, 0) + 1
    return [
        f"{name}-{result.id}" if counts[name] > 1 else name
        for name, result in zip(names, results)
    ]


def _is_excluded(filename: str) -> bool:
    return any(part in EXCLUDED_DIRECTORIES for part in filename.split("/")[:-1])


def export_results_zip(fobj, results, progress_recorder=None):
    """
    Write a ZIP archive containing the result files of the given workflow
    results to `fobj`.

    Members are copied straight from the object store into the archive in
    chunks, so memory use does not scale with the size of the result files.

    Parameters
    ----------
    fobj : file-like object
        Seekable binary stream that receives the archive.
    results : list of topobank.analysis.models.WorkflowResult
        The results to bundle. Should all have completed successfully.
    progress_recorder : topobank.taskapp.tasks.ProgressRecorder, optional
        Reports how many files have been bundled so far, so that a client
        waiting for the archive can show progress.

    Returns
    -------
    None
    """
    # Resolve up front which files will actually go into the archive. A result
    # folder is dominated by the deep-zoom tiles we skip (thousands of them,
    # against a handful of data files), so counting all files would send the
    # progress bar to ~99% in an instant and then leave it there for the whole
    # real work of copying the large files.
    bundles = [
        (
            directory_name,
            result,
            [
                manifest
                for manifest in result.folder.get_valid_files()
                if not _is_excluded(manifest.filename)
            ],
        )
        for directory_name, result in zip(_directory_names(results), results)
    ]

    # One step per bundled file, plus a final one for the README
    nb_steps = 1 + sum(len(manifests) for _, _, manifests in bundles)
    step = 0
    if progress_recorder is not None:
        progress_recorder.set_progress(step, nb_steps, message="Preparing archive")

    with zipfile.ZipFile(fobj, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for directory_name, result, manifests in bundles:
            zip_file.writestr(
                os.path.join(directory_name, "info.txt"), result_info_text(result)
            )

            for manifest in manifests:
                step += 1
                if progress_recorder is not None:
                    progress_recorder.set_progress(
                        step, nb_steps, message=f"Bundling '{result.subject.name}'"
                    )
                try:
                    with manifest.open(mode="rb") as source:
                        with zip_file.open(
                            os.path.join(directory_name, manifest.filename), mode="w"
                        ) as destination:
                            shutil.copyfileobj(source, destination)
                except (OSError, ValueError) as exc:
                    # A missing or unreadable file should not fail the whole
                    # archive; report it in place instead.
                    _log.warning(
                        "Cannot add file '%s' of workflow result %s to ZIP archive: %s",
                        manifest.filename,
                        result.id,
                        exc,
                    )
                    zip_file.writestr(
                        os.path.join(directory_name, f"{manifest.filename}-error.txt"),
                        f"Cannot store file {manifest.filename} in this archive, "
                        f"reason: {exc}\n",
                    )

        zip_file.writestr("README.txt", _readme_text(results))

    if progress_recorder is not None:
        progress_recorder.set_progress(nb_steps, nb_steps, message="Archive complete")
