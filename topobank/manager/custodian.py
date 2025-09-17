import logging

from django.conf import settings
from django.utils import timezone

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

    # Delete all surfaces without creator and owner
    q = Surface.objects.filter(creator__isnull=True, owner__isnull=True)
    if q.count() > 0:
        _log.info(
            f"Custodian: Deleting {q.count()} datasets because they have neither a creator nor an owner."
        )
        q.delete()

    # Delete all ZIP containers (that are just temporary anyway)
    q = ZipContainer.objects.filter(modification_time__lt=timezone.now() - settings.TOPOBANK_DELETE_DELAY)
    if q.count() > 0:
        _log.info(
            f"Custodian: Deleting {q.count()} temporary ZIP containers."
        )
