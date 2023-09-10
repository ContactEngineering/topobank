import logging
import sys

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from celery import chain

from ..manager.models import Topography

from .tasks import renew_bandwidth_cache, renew_squeezed_datafile, renew_topography_images

_log = logging.getLogger(__name__)

# Detect whether we are running within a Celery worker. This solution was suggested here:
# https://stackoverflow.com/questions/39003282/how-can-i-detect-whether-im-running-in-a-celery-worker
_IN_CELERY_WORKER_PROCESS = sys.argv and sys.argv[0].endswith('celery') and 'worker' in sys.argv


@receiver(post_save, sender=Topography)
def post_topography_save(sender, instance, **kwargs):
    #
    # Since the model appears to have changed, we need to regenerate cached properties.
    #
    if instance._refresh_dependent_data:
        if _IN_CELERY_WORKER_PROCESS:
            raise RuntimeError('A Celery worker process updated a significant field on a topography. This would '
                               'retrigger that same worker process again and lead to an infinite loop! Please do not '
                               'update significant fields in Celery worker processes.')
        _log.info(f"Creating squeezed datafile, bandwidth cache and images for {instance.get_subject_type()} "
                  f"{instance.id}...")
        transaction.on_commit(chain(renew_squeezed_datafile.si(instance.id),
                                    renew_bandwidth_cache.si(instance.id),
                                    renew_topography_images.si(instance.id)))
