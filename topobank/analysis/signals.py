import logging

from django.db.models import Q
from django.db.models.signals import post_delete, pre_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone

from ..authorization import get_permission_model
from ..manager.models import Topography, post_refresh_cache
from .models import WorkflowResult

_log = logging.getLogger(__name__)


@receiver(post_delete, sender=WorkflowResult)
def post_delete_analysis(sender, instance, **kwargs):
    """
    Delete the analysis instance, including its associated task and storage files.

    This method performs the following steps:
    1. Cancels the task if it is currently running.
    2. Deletes the database entry for the analysis instance.

    Parameters
    ----------
    *args : tuple
        Variable length argument list.
    **kwargs : dict
        Arbitrary keyword arguments.
    """
    # Cancel task (if running)
    instance.cancel_task()

    # Delete permission set, which triggers deletion of all other associated data.
    # Needs to be in post_delete to avoid recursion.
    try:
        instance.permissions.delete()
    except get_permission_model().DoesNotExist:
        # This permissions set may have been deleted when analysis was deleted in
        # pre_delete_topography. This happens when a surface is deleted, which
        # trigger pre_delete_topography and this triggers pre_delete_analysis twice
        pass


def _surface_scoped_analysis_pks(surface):
    """Primary keys of analyses attached to ``surface`` (legacy FK or M2M).

    A surface-set analysis over surfaces [A, B] has ``subject_surface`` NULL,
    so it is only reachable through the ``surfaces`` M2M. ``distinct()`` is
    required because the M2M join can return a row more than once.
    """
    return list(
        WorkflowResult.objects.filter(
            Q(subject_surface=surface) | Q(surfaces=surface)
        )
        .values_list("pk", flat=True)
        .distinct()
    )


def _related_analysis_pks(instance):
    """Primary keys of all analyses affected by a change to a saved topography.

    Covers the topography's own analysis plus every analysis attached to its
    surface via the legacy FK or the surface-set M2M. Only valid for a saved
    instance (``instance.pk`` set); for a not-yet-saved measurement use
    ``_surface_scoped_analysis_pks`` so ``subject_topography=instance`` does
    not degenerate into an ``IS NULL`` match on unrelated analyses.
    """
    return list(
        WorkflowResult.objects.filter(
            Q(subject_topography=instance)
            | Q(subject_surface=instance.surface)
            | Q(surfaces=instance.surface)
        )
        .values_list("pk", flat=True)
        .distinct()
    )


@receiver(post_refresh_cache, sender=Topography)
def delete_all_related_analyses(sender, instance, **kwargs):
    # Cache is renewed, this means something significant changed and we need to remove
    # the analyses
    _log.debug(
        f"Cache of measurement {instance} was renewed: Marking all affected "
        "analyses as invalid..."
    )
    # Resolve distinct PKs first, then update by pk, so the M2M join cannot
    # duplicate rows or interfere with the update.
    pks = _related_analysis_pks(instance)
    WorkflowResult.objects.filter(pk__in=pks).update(deprecation_time=timezone.now())


@receiver(pre_save, sender=Topography)
def pre_measurement_save(sender, instance, **kwargs):
    created = instance.pk is None
    if created:
        # Measurement was created and added to a dataset: We need to delete the
        # corresponding dataset analysis (both legacy surface analyses and
        # surface-set analyses that include this surface). The instance is not
        # yet saved, so scope by surface only.
        pks = _surface_scoped_analysis_pks(instance.surface)
        analyses = WorkflowResult.objects.filter(pk__in=pks)
        if pks:
            _log.debug(
                "INVALIDATE WORKFLOWS: A measurement was added to dataset "
                f"{instance.surface}: Deleting all affected workflow results with "
                f"ids {', '.join(str(i) for i in pks)}..."
            )
        analyses.delete()


@receiver(pre_delete, sender=Topography)
def pre_delete_topography(sender, instance, **kwargs):
    # The topography analysis is automatically deleted, but we have to delete the
    # corresponding surface analysis; we do this after the transaction has finished
    # so we can check whether the surface still exists.
    _log.debug(f"Measurement {instance} was deleted: Deleting all affected analyses...")
    pks = _related_analysis_pks(instance)
    WorkflowResult.objects.filter(pk__in=pks).delete()
