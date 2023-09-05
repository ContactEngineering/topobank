import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from ..manager.models import Topography, Surface
from .controller import renew_analyses_for_subject

_log = logging.getLogger(__name__)


@receiver(post_save, sender=Topography)
def renew_dataset_analyses(sender, instance, **kwargs):
    renew_analyses_for_subject(instance)


@receiver(post_save, sender=Surface)
def renew_container_analyses(sender, instance, **kwargs):
    renew_analyses_for_subject(instance)

# FIXME!!! Do we need a trigger when saving collections?
