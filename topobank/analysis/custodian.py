import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Q, RestrictedError
from django.utils import timezone

from ..taskapp.celeryapp import app
from .models import WorkflowResult
from .zip_model import ResultZipContainer

_log = logging.getLogger(__name__)


def _delete_tolerating_restrict(queryset, description):
    """Delete the queryset's rows, skipping those protected by a RESTRICT reference.

    Downstream plugins may guard workflow results with RESTRICT foreign keys
    (e.g. a result a trained model was built from). A bulk delete aborts
    wholesale on the first protected row, so fall back to per-row deletes
    and leave protected rows for a later run, once their guard clears.
    """
    try:
        queryset.delete()
    except RestrictedError:
        skipped = 0
        for obj in queryset.iterator():
            try:
                obj.delete()
            except RestrictedError:
                skipped += 1
        if skipped:
            _log.info(
                "Custodian: skipped %d %s protected by RESTRICT references.",
                skipped,
                description,
            )


@app.task
def periodic_cleanup():
    # Delete all workflow results that were marked as deprecated and that are
    # not saved
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
            # Soft-deleted rows belong to the retention clause below; they stay
            # restorable until their window closes.
            deleted_at__isnull=True,
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
            f"Custodian: Deleting {len(deprecated_pks)} workflow results because "
            "they were marked as deprecated."
        )
        _delete_tolerating_restrict(
            WorkflowResult.objects.filter(pk__in=deprecated_pks),
            "deprecated workflow results",
        )

    # Delete all workflow results that were soft-deleted longer than the retention
    # window ago. Independent of the deprecation clause above: stamped rows
    # are purged regardless of ``name`` and regardless of whether a subject
    # link survives — a soft-deleted result belongs to a deleted container,
    # and its subject links may already be gone.
    soft_deleted = WorkflowResult.objects.filter(
        deleted_at__lt=timezone.now() - settings.TOPOBANK_DELETE_DELAY
    )
    count = soft_deleted.count()
    if count:
        _log.info(
            "Custodian: Deleting %d workflow results because they were "
            "soft-deleted more than %s ago.",
            count,
            settings.TOPOBANK_DELETE_DELAY,
        )
        _delete_tolerating_restrict(soft_deleted, "soft-deleted workflow results")

    # Delete all ZIP containers of workflow results (they are just temporary
    # download bundles and can be rebuilt at any time)
    temporary_delay = getattr(
        settings, "TOPOBANK_TEMPORARY_DELAY", settings.TOPOBANK_DELETE_DELAY
    )
    q = ResultZipContainer.objects.filter(
        updated_at__lt=timezone.now() - temporary_delay
    )
    count = q.count()
    if count:
        _log.info(
            f"Custodian: Deleting {count} temporary ZIP containers of workflow results."
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
        q.update(
            task_state=WorkflowResult.FAILURE, task_error="Workflow failed to launch."
        )
