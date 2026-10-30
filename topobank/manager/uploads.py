"""Confirming an uploaded data file and starting its processing.

A measurement's data file is uploaded straight to storage, ahead of anything
reading it. Two things then have to happen exactly once: the manifest is
confirmed (`Manifest.confirm_upload`), and the measurement's processing is
dispatched. Several parties may get there first -- the storage's upload
notification, a reader of the file (which only confirms it), a periodic sweep
-- so both steps are conditional updates that any number of callers can make;
whoever comes later finds nothing left to do.
"""

import logging
from typing import List, NamedTuple, Optional

from django.db import transaction
from django.db.models import Q

from ..files.models import Manifest
from ..taskapp.models import TaskStateModel
from ..taskapp.utils import run_task
from .models import Topography

_log = logging.getLogger(__name__)


def dispatch_processing(manifest: Manifest) -> List[Topography]:
    """Start processing the measurements whose data file is `manifest`.

    Only measurements that were never processed are dispatched; a measurement
    whose processing is queued, under way or done is left alone, and so is one
    whose processing failed, even for want of the file (an edit of a
    significant field before the upload arrived dispatches a run that fails
    that way; the user's next edit or recompute reprocesses it). Returns the
    measurements dispatched, each carrying the task id of its dispatch.
    """
    if manifest.kind != "raw" or not manifest.file:
        return []
    dispatched = []
    for topography in Topography.objects.filter(
        datafile=manifest, task_state=TaskStateModel.NOTRUN
    ):
        if run_task(topography, from_states=(TaskStateModel.NOTRUN,)):
            dispatched.append(topography)
            _log.info(
                "Dispatched the processing of topography %s for the upload of %s.",
                topography.id,
                manifest,
            )
    return dispatched


def confirm_and_dispatch(manifest: Manifest) -> Optional[List[Topography]]:
    """Confirm the upload of `manifest`, if it has arrived, and process it.

    The single entry point that starts the processing of an upload: the
    storage's notification, a sweep over unconfirmed uploads, or a caller that
    means to. Returns None if the file is not there, else the
    measurements this call dispatched (see `dispatch_processing`), which is
    empty when they were dispatched already. Both steps are idempotent, so
    repeated and concurrent calls confirm and dispatch once.
    """
    # The storage round trip of confirming stays outside the transaction
    if not manifest.confirm_upload():
        return None
    with transaction.atomic():
        return dispatch_processing(manifest)


def unconfirmed_uploads(older_than):
    """The manifests created before `older_than` whose upload is unconfirmed.

    The archive of a ZIP container is not among them: whoever handles the
    container confirms it, and it goes with the container.
    """
    return Manifest.objects.filter(
        Q(file__isnull=True) | Q(file=""),
        confirmed_at__isnull=True,
        created_at__lt=older_than,
        zip_containers__isnull=True,
    )


class UploadSweep(NamedTuple):
    """What `sweep_unconfirmed_uploads` found."""

    #: Uploads that had arrived unnoticed: confirmed, and the data files among
    #: them processed
    confirmed: List[Manifest]
    #: Uploads that are not in storage: they never arrived
    missing: List[Manifest]


def sweep_unconfirmed_uploads(older_than) -> UploadSweep:
    """Confirm and process the uploads that arrived without anyone noticing.

    The storage's notification of an upload can be lost, and nothing may read
    the file before the custodian comes to delete the manifest of an upload
    that never arrived. This looks in storage for every unconfirmed upload
    created before `older_than` (one round trip each, see
    `Manifest.confirm_upload`) and runs `confirm_and_dispatch` on those that
    are there. Returns the manifests it confirmed and those it found missing;
    one that storage could not be asked about (unreachable, say) is neither,
    so that the custodian does not delete the manifest of an upload that is
    there.
    """
    confirmed = []
    missing = []
    for manifest in unconfirmed_uploads(older_than).iterator():
        try:
            arrived = manifest.confirm_upload(raise_storage_errors=True)
        except Exception as exc:
            _log.warning(
                "Sweep: could not check whether the upload of %s arrived: %s",
                manifest,
                exc,
            )
            continue
        if not arrived:
            missing.append(manifest)
            continue
        confirmed.append(manifest)
        _log.info(
            "Sweep: confirmed the upload of %s, which arrived unnoticed.", manifest
        )
        # Finds the upload confirmed and dispatches, without another round trip
        confirm_and_dispatch(manifest)
    return UploadSweep(confirmed, missing)
