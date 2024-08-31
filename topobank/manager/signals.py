import logging

from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver
from notifications.models import Notification

from .models import Surface, Topography

_log = logging.getLogger(__name__)


def _remove_notifications(instance):
    ct = ContentType.objects.get_for_model(instance)
    Notification.objects.filter(
        target_object_id=instance.id, target_content_type=ct
    ).delete()


@receiver(pre_delete, sender=Topography)
def pre_delete_topography(sender, instance, using, **kwargs):
    _remove_notifications(instance)
    instance.remove_files()


@receiver(post_delete, sender=Surface)
def post_delete_surface(sender, instance, using, **kwargs):
    _remove_notifications(instance)
    # Delete permission set, which triggers deletion of all other associated data.
    # Needs to be in post_delete to avoid recursion.
    instance.permissions.delete()
