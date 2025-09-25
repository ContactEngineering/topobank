import logging

from django.conf import settings
from django.utils import timezone

from ..taskapp.celeryapp import app
from .models import WorkflowResult

_log = logging.getLogger(__name__)


@app.task
def periodic_cleanup():
    # Delete all analyses that were marked as deprecated and that are not saved
    q = WorkflowResult.objects.filter(
        deprecation_time__lt=timezone.now() - settings.TOPOBANK_DELETE_DELAY,
        subject_dispatch__isnull=False,
        name__isnull=True
    )
    if q.count() > 0:
        _log.info(
            f"Custodian: Deleting {q.count()} analysis results because they were marked as deprecated."
        )
        q.delete()
