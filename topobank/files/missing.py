"""
Detect and report files that the database refers to but storage no longer has.

A manifest with a confirmed upload points to an object in storage. If that
object is gone, e.g. because it was deleted by mistake, every read of it fails
with a FileNotFoundError deep inside the storage backend. Reading through
`missing_file_guard` turns that into a `MissingFileError` and emails the site
admins, so lost data is noticed instead of surfacing as unrelated errors.
"""

import logging
import traceback
from contextlib import contextmanager

from django.conf import settings
from django.core.cache import cache
from django.core.mail import mail_admins

_log = logging.getLogger(__name__)

#: Report a missing file at most once per this many seconds
DEFAULT_REPORT_INTERVAL = 24 * 60 * 60


class MissingFileError(FileNotFoundError):
    """A file that should exist in storage does not."""

    def __init__(self, manifest, storage_name):
        self.manifest = manifest
        self.storage_name = storage_name
        super().__init__(
            f"File '{storage_name}' of manifest {manifest.pk} does not exist in storage"
        )


def _referrers(manifest) -> list[str]:
    """Describe the measurements and datasets that use a manifest."""
    from django.db.models import Q

    from ..manager.models import Surface, Topography

    lines = []
    for topography in Topography.all_objects.filter(
        Q(datafile=manifest) | Q(squeezed_datafile=manifest) | Q(thumbnail=manifest)
    ):
        lines.append(
            f"Measurement {topography.pk} ('{topography.name}') "
            f"of dataset {topography.surface_id}"
        )
    if manifest.folder_id is not None:
        for topography in Topography.all_objects.filter(
            Q(attachments_id=manifest.folder_id) | Q(deepzoom_id=manifest.folder_id)
        ):
            lines.append(
                f"Folder of measurement {topography.pk} ('{topography.name}') "
                f"of dataset {topography.surface_id}"
            )
        for surface in Surface.all_objects.filter(attachments_id=manifest.folder_id):
            lines.append(f"Attachments of dataset {surface.pk} ('{surface.name}')")
    return lines


def report_missing_file(manifest, storage_name: str):
    """
    Log a missing file and email the site admins about it.

    The email is sent at most once per `TOPOBANK_MISSING_FILE_REPORT_INTERVAL`
    seconds for each manifest, so a frequently visited page does not flood the
    admins. Reporting never raises: it must not hide the original error.
    """
    _log.error(f"File '{storage_name}' of manifest {manifest.pk} is missing in storage")
    try:
        interval = getattr(
            settings, "TOPOBANK_MISSING_FILE_REPORT_INTERVAL", DEFAULT_REPORT_INTERVAL
        )
        # `add` is False if the key exists, i.e. we reported recently. A cache
        # that is down (None) must not suppress the report.
        if cache.add(f"topobank-missing-file-{manifest.pk}", True, interval) is False:
            return

        try:
            referrers = _referrers(manifest) or ["(none found)"]
        except Exception as exc:  # noqa: BLE001 - this is diagnostic output only
            referrers = [f"(could not be determined: {exc})"]
        # Where the file was needed, without this module's own frames
        where = "".join(traceback.format_stack(limit=12)[:-3])

        mail_admins(
            f"Missing file in storage: manifest {manifest.pk} ({manifest.filename})",
            "A file that the database refers to does not exist in storage.\n\n"
            f"Manifest:     {manifest.pk}\n"
            f"File name:    {manifest.filename}\n"
            f"Kind:         {manifest.kind}\n"
            f"Storage name: {storage_name}\n"
            f"Folder:       {manifest.folder_id}\n"
            f"Uploaded:     {manifest.confirmed_at}\n\n"
            "Used by:\n" + "\n".join(f"  {line}" for line in referrers) + "\n\n"
            "Where it was needed (most recent call last):\n" + where + "\n"
            f"This file is reported at most once every {interval} seconds.",
            fail_silently=True,
        )
    except Exception:  # noqa: BLE001
        _log.exception(f"Could not report missing file of manifest {manifest.pk}")


@contextmanager
def missing_file_guard(manifest):
    """
    Report and re-raise as `MissingFileError` if the manifest's file is missing
    in storage while the enclosed code reads it.
    """
    try:
        yield
    except MissingFileError:
        raise  # Already reported by an inner guard
    except FileNotFoundError as exc:
        storage_name = manifest.file.name if manifest.file else manifest.filename
        report_missing_file(manifest, storage_name)
        raise MissingFileError(manifest, storage_name) from exc
