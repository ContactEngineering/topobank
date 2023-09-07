import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from ..manager.models import Topography, Surface
from .controller import renew_analyses_for_subject

_log = logging.getLogger(__name__)


@receiver(post_save, sender=Topography)
def post_topography_save(sender, instance, **kwargs):
    renew_analyses_for_subject(instance)


@receiver(post_delete, sender=Topography)
def post_topography_delete(sender, instance, **kwargs):
    # Topography analysis is automatically deleted, but we have to renew the corresponding surface analysis
    renew_analyses_for_subject(instance.surface)


@receiver(post_save, sender=Surface)
def post_surface_save(sender, instance, **kwargs):
    renew_analyses_for_subject(instance)

# FIXME!!! Do we need a trigger when saving collections?
