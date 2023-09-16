import logging
import sys

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from celery import chain

from ..manager.models import Topography

from .tasks import renew_topography_cache

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
        if not _IN_CELERY_WORKER_PROCESS:
            # Don' trigger this from inside a Celery worker, otherwise we'd have an infinite loop
            _log.info(f"Renewing cached properties of {instance.get_subject_type()} {instance.id}...")
            transaction.on_commit(renew_topography_cache.si(instance.id))
