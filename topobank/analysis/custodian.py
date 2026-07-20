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
    analysis_delay = getattr(
        settings, "TOPOBANK_ANALYSIS_DELETE_DELAY", settings.TOPOBANK_DELETE_DELAY
    )
    # Resolve distinct PKs first: including the surfaces M2M in the filter
    # introduces a join that can return a row more than once, and ``.delete()``
    # cannot follow ``.distinct()``.
    deprecated_pks = list(
        WorkflowResult.objects.filter(
            deprecation_time__lt=timezone.now() - analysis_delay,
            name__isnull=True,
        )
        .filter(
            Q(subject_topography__isnull=False)
            | Q(subject_surface__isnull=False)
            | Q(subject_tag__isnull=False)
            | Q(surfaces__isnull=False)
        )
        .values_list("pk", flat=True)
        .distinct()
    )
    if deprecated_pks:
        _log.info(
            f"Custodian: Deleting {len(deprecated_pks)} analysis results because "
            "they were marked as deprecated."
        )
        WorkflowResult.objects.filter(pk__in=deprecated_pks).delete()

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
        q.update(task_state=WorkflowResult.FAILURE, task_error="Analysis failed to launch.")
