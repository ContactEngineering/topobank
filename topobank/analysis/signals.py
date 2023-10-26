import logging
import sys

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from ..manager.models import Topography, Surface, cache_renewed
from .controller import renew_analyses_for_subject

_log = logging.getLogger(__name__)

# Detect whether we are running within a Celery worker. This solution was suggested here:
# https://stackoverflow.com/questions/39003282/how-can-i-detect-whether-im-running-in-a-celery-worker
_IN_CELERY_WORKER_PROCESS = sys.argv and sys.argv[0].endswith('celery') and 'worker' in sys.argv


@receiver(cache_renewed, sender=Topography)
def cache_renewed(sender, instance, **kwargs):
    # Cache is renewed, this means something significant changed and we need to renew the analyses
    renew_analyses_for_subject(instance)


@receiver(post_delete, sender=Topography)
def post_topography_delete(sender, instance, **kwargs):
    # Topography analysis is automatically deleted, but we have to renew the corresponding surface analysis
    renew_analyses_for_subject(instance.surface)


# FIXME!!! Do we need this? The surface has no metadata that affects analyses
#@receiver(post_save, sender=Surface)
#def post_surface_save(sender, instance, **kwargs):
#    # Since the surface appears to have changed, we need to regenerate the analyses.
#    renew_analyses_for_subject(instance)

# FIXME!!! Do we need a trigger when saving collections?
