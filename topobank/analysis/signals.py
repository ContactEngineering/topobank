import logging
import sys

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from ..manager.models import Surface, Topography, post_renew_cache
from .controller import renew_analyses_for_subject

_log = logging.getLogger(__name__)

# Detect whether we are running within a Celery worker. This solution was suggested here:
# https://stackoverflow.com/questions/39003282/how-can-i-detect-whether-im-running-in-a-celery-worker
_IN_CELERY_WORKER_PROCESS = sys.argv and sys.argv[0].endswith('celery') and 'worker' in sys.argv


@receiver(post_renew_cache, sender=Topography)
def cache_renewed(sender, instance, **kwargs):
    # Cache is renewed, this means something significant changed and we need to renew the analyses
    _log.debug(f'Received `post_renew_cache` signal on {instance}')
    renew_analyses_for_subject(instance)


@receiver(post_delete, sender=Topography)
def post_topography_delete(sender, instance, **kwargs):
    def do_renew(id):
        try:
            surface_instance = Surface.objects.get(pk=id)
            renew_analyses_for_subject(surface_instance)
        except Surface.DoesNotExist:
            # The surface may no longer exist if this delete was called on a cascade from the deletion of a surface
            pass

    # Topography analysis is automatically deleted, but we have to renew the corresponding surface analysis; we do
    # this after the transaction has finished so we can check whether the surface still exists.
    surface_id = instance.surface.id
    transaction.on_commit(lambda: do_renew(surface_id))

# FIXME!!! Do we need this? The surface has no metadata that affects analyses
# @receiver(post_save, sender=Surface)
# def post_surface_save(sender, instance, **kwargs):
#    # Since the surface appears to have changed, we need to regenerate the analyses.
#    renew_analyses_for_subject(instance)

# FIXME!!! Do we need a trigger when saving collections?
