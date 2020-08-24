from django.db.models.signals import post_save
from django.dispatch import receiver
import short_url
import logging

from .models import Publication

_log = logging.getLogger(__name__)


@receiver(post_save, sender=Publication)
def set_short_url(sender, instance, **kwargs):
    if instance.short_url is None:
        instance.short_url = short_url.encode_url(instance.id)
        instance.save()
