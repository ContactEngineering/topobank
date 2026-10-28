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
from typing import List, Optional

from django.db import transaction

from ..files.models import Manifest
from ..taskapp.models import TaskStateModel
from ..taskapp.utils import run_task
from .models import Topography

_log = logging.getLogger(__name__)


def dispatch_processing(manifest: Manifest) -> List[Topography]:
    """Start processing the measurements whose data file is `manifest`.

    Only measurements that were never processed are dispatched; a measurement
    whose processing is queued, under way or done is left alone. Returns the
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
