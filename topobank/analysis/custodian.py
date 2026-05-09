import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from ..taskapp.celeryapp import app
from .models import WorkflowResult

_log = logging.getLogger(__name__)


@app.task
def periodic_cleanup():
    # Delete all analyses that were marked as deprecated and that are not saved
    q = WorkflowResult.objects.filter(
        deprecation_time__lt=timezone.now() - settings.TOPOBANK_DELETE_DELAY,
        name__isnull=True
    ).filter(
        Q(subject_topography__isnull=False) | Q(subject_surface__isnull=False) | Q(subject_tag__isnull=False)
    )
    if q.count() > 0:
        _log.info(
            f"Custodian: Deleting {q.count()} analysis results because they were marked as deprecated."
        )
        q.delete()

    # Update WorkflowResults stuck in pending state with no Celery task assigned
    q = WorkflowResult.objects.filter(
        task_state=WorkflowResult.PENDING,
        task_id__isnull=True,
        created_at__lt=timezone.now() - timedelta(days=1),
    )
    if q.count() > 0:
        _log.info(
            f"Custodian: Updating {q.count()} workflow results because they are stuck in pending state"
            " with no task assigned."
        )
        q.update(task_state=WorkflowResult.FAILED, error_message="Analysis failed to launch.")
