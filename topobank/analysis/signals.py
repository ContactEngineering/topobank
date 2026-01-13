import logging
import sys

from django.db.models import Q
from django.db.models.signals import post_delete, pre_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone

from ..authorization.models import PermissionSet
from ..manager.models import Topography, post_refresh_cache
from .models import WorkflowResult

_log = logging.getLogger(__name__)

# Detect whether we are running within a Celery worker. This solution was suggested here:
# https://stackoverflow.com/questions/39003282/how-can-i-detect-whether-im-running-in-a-celery-worker
_IN_CELERY_WORKER_PROCESS = (
    sys.argv and sys.argv[0].endswith("celery") and "worker" in sys.argv
)


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
    except PermissionSet.DoesNotExist:
        # This permissions set may have been deleted when analysis was deleted in
        # pre_delete_topography. This happens when a surface is deleted, which
        # trigger pre_delete_topography and this triggers pre_delete_analysis twice
        pass


@receiver(post_refresh_cache, sender=Topography)
def delete_all_related_analyses(sender, instance, **kwargs):
    # Cache is renewed, this means something significant changed and we need to remove
    # the analyses
    _log.debug(
        f"Cache of measurement {instance} was renewed: Marking all affected "
        "analyses as invalid..."
    )
    # Use update() directly for better performance
    WorkflowResult.objects.filter(
        Q(subject_dispatch__topography=instance)
        | Q(subject_dispatch__surface=instance.surface)
    ).update(deprecation_time=timezone.now())


@receiver(pre_save, sender=Topography)
def pre_measurement_save(sender, instance, **kwargs):
    created = instance.pk is None
    if created:
        # Measurement was created and added to a dataset: We need to delete the
        # corresponding dataset analysis
        analyses = WorkflowResult.objects.filter(subject_dispatch__surface=instance.surface)
        if analyses.exists():  # More efficient than count() > 0
            ids = ", ".join(
                [str(i) for i in analyses.values_list("id", flat=True)]
            )
            _log.debug(
                "INVALIDATE WORKFLOWS: A measurement was added to dataset "
                f"{instance.surface}: Deleting all affected workflow results with "
                f"ids {ids}..."
            )
        analyses.delete()


@receiver(pre_delete, sender=Topography)
def pre_delete_topography(sender, instance, **kwargs):
    # The topography analysis is automatically deleted, but we have to delete the
    # corresponding surface analysis; we do this after the transaction has finished
    # so we can check whether the surface still exists.
    _log.debug(f"Measurement {instance} was deleted: Deleting all affected analyses...")
    WorkflowResult.objects.filter(subject_dispatch__surface=instance.surface).delete()
