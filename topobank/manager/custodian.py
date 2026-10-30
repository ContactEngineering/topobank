import logging

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from topobank.files.models import Manifest

from ..taskapp.celeryapp import app
from ..taskapp.utils import delete_tolerating_restrict
from .models import Surface, Topography
from .uploads import sweep_unconfirmed_uploads
from .zip_model import ZipContainer

_log = logging.getLogger(__name__)


@app.task
def periodic_cleanup():
    # Transient artifacts (download bundles, abandoned uploads) get a shorter
    # grace period than user-recoverable soft-deleted datasets.
    temporary_delay = getattr(
        settings, "TOPOBANK_TEMPORARY_DELAY", settings.TOPOBANK_DELETE_DELAY
    )

    # Delete all topographies that were marked for deletion
    q = Topography.all_objects.filter(
        deleted_at__lt=timezone.now() - settings.TOPOBANK_DELETE_DELAY
    )
    if q.count() > 0:
        _log.info(
            f"Custodian: Deleting {q.count()} measurements because they were marked for deletion."
        )
        # A downstream RESTRICT (e.g. sds-api's PredictionResult on a
        # measurement's workflow result) must not abort the whole purge and
        # the steps after it.
        delete_tolerating_restrict(q, "soft-deleted measurements")

    # Delete all surfaces that were marked for deletion
    q = Surface.all_objects.filter(
        deleted_at__lt=timezone.now() - settings.TOPOBANK_DELETE_DELAY
    )
    if q.count() > 0:
        _log.info(
            f"Custodian: Deleting {q.count()} datasets because they were marked for deletion."
        )
        delete_tolerating_restrict(q, "soft-deleted datasets")

    # Delete all surfaces without created_by and owned_by
    q = Surface.all_objects.filter(created_by__isnull=True, owned_by__isnull=True)
    if q.count() > 0:
        _log.info(
            f"Custodian: Deleting {q.count()} datasets because they have neither a created_by nor an owned_by."
        )
        delete_tolerating_restrict(q, "orphaned datasets")

    # Delete all ZIP containers (that are just temporary anyway)
    q = ZipContainer.objects.filter(updated_at__lt=timezone.now() - temporary_delay)
    if q.count() > 0:
        _log.info(
            f"Custodian: Deleting {q.count()} temporary ZIP containers."
        )
        q.delete()

    # An upload that arrived but whose notification was lost is confirmed and
    # processed rather than deleted with the uploads that never arrived
    cutoff = timezone.now() - temporary_delay
    confirmed = sweep_unconfirmed_uploads(cutoff)
    if confirmed:
        _log.info(
            f"Custodian: Confirmed {len(confirmed)} uploads that arrived unnoticed."
        )

    # Delete all Manifests that are not confirmed, have no file, and too old
    q = Manifest.objects.filter(
        Q(file__isnull=True) | Q(file=""),
        created_at__lt=cutoff,
        confirmed_at__isnull=True,
    )
    if q.count() > 0:
        _log.info(
            f"Custodian: Deleting {q.count()} unlinked Manifests."
        )
        q.delete()
