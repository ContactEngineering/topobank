import logging

from django.conf import settings
from django.utils import timezone

from topobank.files.models import Manifest

from ..taskapp.celeryapp import app
from .models import Surface, Topography
from .zip_model import ZipContainer

_log = logging.getLogger(__name__)


@app.task
def periodic_cleanup():
    # Delete all topographies that were marked for deletion
    q = Topography.objects.filter(
        deletion_time__lt=timezone.now() - settings.TOPOBANK_DELETE_DELAY
    )
    if q.count() > 0:
        _log.info(
            f"Custodian: Deleting {q.count()} measurements because they were marked for deletion."
        )
        q.delete()

    # Delete all surfaces that were marked for deletion
    q = Surface.objects.filter(
        deletion_time__lt=timezone.now() - settings.TOPOBANK_DELETE_DELAY
    )
    if q.count() > 0:
        _log.info(
            f"Custodian: Deleting {q.count()} datasets because they were marked for deletion."
        )
        q.delete()

    # Delete all surfaces without created_by and owned_by
    q = Surface.objects.filter(created_by__isnull=True, owned_by__isnull=True)
    if q.count() > 0:
        _log.info(
            f"Custodian: Deleting {q.count()} datasets because they have neither a created_by nor an owned_by."
        )
        q.delete()

    # Delete all ZIP containers (that are just temporary anyway)
    q = ZipContainer.objects.filter(updated_at__lt=timezone.now() - settings.TOPOBANK_DELETE_DELAY)
    if q.count() > 0:
        _log.info(
            f"Custodian: Deleting {q.count()} temporary ZIP containers."
        )
        q.delete()

    # Delete all Manifests that are not linked to any Topography or Folder
    q = Manifest.objects.filter(
        created_at__lt=timezone.now() - settings.TOPOBANK_DELETE_DELAY,
        topography__isnull=True,
        folder__isnull=True
    )
    if q.count() > 0:
        _log.info(
            f"Custodian: Deleting {q.count()} unlinked Manifests."
        )
        q.delete()
