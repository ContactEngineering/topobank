"""Processing steps: the derived files a deployment generates for a measurement.

Inspecting a data file has two parts. Reading its metadata (channels, sizes,
units, instrument, bandwidth, ...) is the same for every deployment and lives in
`topobank.manager.processing`. Which derived files are generated from the data
depends on what the deployment's frontend needs: contact.engineering shows
thumbnails and deep zoom images, surface.design additionally computes mesh maps.
Each such file (or set of files) is written by a *step*, and the steps a
deployment runs are listed in the setting ``TOPOBANK_PROCESSING_STEPS``.

All files of a measurement's steps go into one folder, `Topography.derived`, under
names that are fixed per step (`thumbnail.<format>`, `squeezed.nc`, `dzi.json`
and `dzi_files/...`, ...). A step names the files it owns with `owns`, so that one
step's files can be regenerated without the others'.

A step is any object with these attributes (no base class is required, so a
package can provide a step without depending on topobank):

``name`` : str
    Unique name; the key of the step in an `InspectionResult` and in
    `Topography.processing_steps`.
``version`` : str
    Changes whenever the files the step writes change. A measurement processed
    with another version (or other options) counts as out of date (see the
    management command ``reprocess_outdated``).
``required`` : bool
    Whether a measurement is incomplete without the step's files. A failure of
    any step is recorded and logged and does not fail the processing; that of a
    required step is logged as an error.
``applies_to(adapter) -> bool``
    Whether the step applies to measurements of the kind `adapter` handles
    (see `topobank.manager.kinds`).
``owns(filename) -> bool``
    Whether `filename` in the derived folder is one of the step's files.
``write(data, adapter, params, options, save) -> None``
    Write the step's files for the data object `data`, handing each local file to
    `save(filename, path)`. `params` are the measurement's
    `InspectionParameters`, `options` the step's entry of
    ``TOPOBANK_PROCESSING_STEP_OPTIONS`` (a dict, empty by default).

The steps are named in the processing request (`InspectionParameters.steps`) by
the name of a built-in step or the import path of an object (or a class, which is
instantiated), so that a processing backend in another process needs no Django
settings to resolve them; it needs only the packages that provide them.

Like `topobank.manager.processing`, this module imports no Django.
"""

import hashlib
import importlib
import json
import tempfile

from .kinds import CANONICAL_DATAFILE_FORMAT

#: Name of the squeezed datafile in the derived folder
SQUEEZED_FILENAME = f"squeezed.{CANONICAL_DATAFILE_FORMAT}"
#: Stem of the thumbnail's name in the derived folder (`thumbnail.<format>`)
THUMBNAIL_STEM = "thumbnail"
#: Name of the deep zoom images' descriptor in the derived folder
DEEPZOOM_FILENAME = "dzi.json"


class SqueezedStep:
    """The squeezed datafile: the measurement with all its filters applied, as
    NetCDF, which `Topography.read` reads instead of the raw file.

    Every deployment runs it: analyses rely on it.
    """

    name = "squeezed"
    version = "1"
    required = True

    def applies_to(self, adapter):
        return adapter.has_canonical_file

    def owns(self, filename):
        return filename == SQUEEZED_FILENAME

    def write(self, data, adapter, params, options, save):
        with tempfile.NamedTemporaryFile(suffix=f".{CANONICAL_DATAFILE_FORMAT}") as tmp:
            adapter.write_canonical_file(data, tmp.name)
            save(SQUEEZED_FILENAME, tmp.name)


class ThumbnailStep:
    """A thumbnail image, `thumbnail.<TOPOBANK_THUMBNAIL_FORMAT>`."""

    name = "thumbnail"
    version = "1"
    required = True

    def applies_to(self, adapter):
        return True

    def owns(self, filename):
        return filename.startswith(f"{THUMBNAIL_STEM}.")

    def write(self, data, adapter, params, options, save):
        from .processing import visualization_topography

        image = adapter.render_thumbnail(
            visualization_topography(
                data, params.detrend_mode, params.visualization_detrend_mode
            ),
            format=params.thumbnail_format,
        )
        with tempfile.NamedTemporaryFile() as tmp:
            tmp.write(image.getvalue())
            tmp.flush()
            save(f"{THUMBNAIL_STEM}.{params.thumbnail_format}", tmp.name)


class DeepZoomStep:
    """Deep zoom images (JPEG tiles and NetCDF tiles) of a map: `dzi.json`,
    `dzi_files/...`, `dzi-nc.json` and `dzi-nc_files/...`."""

    name = "deepzoom"
    version = "1"
    required = True

    def applies_to(self, adapter):
        return adapter.has_deepzoom

    def owns(self, filename):
        return filename.split("/", 1)[0] in (
            "dzi.json",
            "dzi_files",
            "dzi-nc.json",
            "dzi-nc_files",
        )

    def write(self, data, adapter, params, options, save):
        from .processing import visualization_topography

        adapter.write_deepzoom(
            visualization_topography(
                data, params.detrend_mode, params.visualization_detrend_mode
            ),
            save,
        )


#: The built-in steps, by name
BUILTIN_STEPS = {
    step.name: step for step in (SqueezedStep(), ThumbnailStep(), DeepZoomStep())
}

#: The steps every deployment runs, whatever it configures
MANDATORY_STEPS = (SqueezedStep.name,)

#: The steps of a deployment that configures none (`TOPOBANK_PROCESSING_STEPS`)
DEFAULT_STEPS = (SqueezedStep.name, ThumbnailStep.name, DeepZoomStep.name)


def _import(path):
    module_path, _, attribute = path.rpartition(".")
    if not module_path:
        raise ImportError(f"'{path}' is neither a built-in step nor an import path.")
    return getattr(importlib.import_module(module_path), attribute)


_resolved = {}


def resolve_step(spec):
    """The step `spec` names: a built-in step's name, or the import path of a step
    object (or of a class, which is instantiated once)."""
    if spec in BUILTIN_STEPS:
        return BUILTIN_STEPS[spec]
    try:
        return _resolved[spec]
    except KeyError:
        pass
    step = _import(spec)
    if isinstance(step, type):
        step = step()
    for attribute in ("name", "version", "applies_to", "owns", "write"):
        if not hasattr(step, attribute):
            raise TypeError(f"Processing step '{spec}' has no `{attribute}`.")
    _resolved[spec] = step
    return step


def resolve_steps(specs):
    """The steps `specs` name, mandatory steps first and each name once."""
    steps = {}
    for spec in tuple(MANDATORY_STEPS) + tuple(specs):
        step = resolve_step(spec)
        if step.name in steps and steps[step.name] is not step:
            raise ValueError(f"Two processing steps are named '{step.name}'.")
        steps[step.name] = step
    return list(steps.values())


def step_version(step, options=None):
    """The version a step's files are recorded with: its own version, and, where
    the deployment passes it options, a digest of them, so that changing the
    options makes measurements out of date just as a new version does."""
    version = str(step.version)
    if options:
        digest = hashlib.sha256(
            json.dumps(options, sort_keys=True, default=str).encode()
        ).hexdigest()[:12]
        version = f"{version}+{digest}"
    return version
