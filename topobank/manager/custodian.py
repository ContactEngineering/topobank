import logging

from django.conf import settings
from django.utils import timezone

from ..taskapp.celeryapp import app

from .models import Surface, Topography

_log = logging.getLogger(__name__)


@app.task
def periodic_cleanup():
    # Delete all topographies that were marked for deletion
    q = Topography.objects.filter(
        deletion_time__lt=timezone.now() - settings.TOPOBANK_DELETION_DELAY
    )
    if q.count() > 0:
        _log.info(
            f"Custodian: Deleting {q.count()} measurements because they were marked for deletion."
        )

    # Delete all surfaces that were marked for deletion
    q = Surface.objects.filter(
        deletion_time__lt=timezone.now() - settings.TOPOBANK_DELETION_DELAY
    )
    if q.count() > 0:
        _log.info(
            f"Custodian: Deleting {q.count()} datasets because they were marked for deletion."
        )

    # Delete all surfaces without creator and owner
    q = Surface.objects.filter(creator__is_null=True, owner__is_null=True)
    if q.count() > 0:
        _log.info(
            f"Custodian: Deleting {q.count()} datasets because they have neither a creator nor an owner."
        )
