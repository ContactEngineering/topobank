import logging
import sys

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from ..manager.models import Topography, Surface
from .controller import renew_analyses_for_subject

_log = logging.getLogger(__name__)

# Detect whether we are running within a Celery worker. This solution was suggested here:
# https://stackoverflow.com/questions/39003282/how-can-i-detect-whether-im-running-in-a-celery-worker
_IN_CELERY_WORKER_PROCESS = sys.argv and sys.argv[0].endswith('celery') and 'worker' in sys.argv


@receiver(post_save, sender=Topography)
def post_topography_save(sender, instance, **kwargs):
    #
    # Since the topography appears to have changed, we need to regenerate the analyses.
    #
    if instance._refresh_dependent_data:
        if not _IN_CELERY_WORKER_PROCESS and instance.is_metadata_complete:
            # Don' trigger this from inside a Celery worker, otherwise we'd have an infinite loop
            #renew_analyses_for_subject(instance)
            pass


@receiver(post_delete, sender=Topography)
def post_topography_delete(sender, instance, **kwargs):
    # Topography analysis is automatically deleted, but we have to renew the corresponding surface analysis
    renew_analyses_for_subject(instance.surface)


@receiver(post_save, sender=Surface)
def post_surface_save(sender, instance, **kwargs):
    #
    # Since the surface appears to have changed, we need to regenerate the analyses.
    #
    renew_analyses_for_subject(instance)

# FIXME!!! Do we need a trigger when saving collections?
